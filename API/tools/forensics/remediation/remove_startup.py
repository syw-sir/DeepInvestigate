"""
启动项清理工具 (v4.1)

删除恶意启动项（注册表/计划任务/服务）。风险等级：Level 3（必须 HITL 审批）。
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

# 系统关键服务白名单（绝对不可操作）
PROTECTED_SERVICES = {
    "Dhcp", "Dnscache", "eventlog", "EventSystem", "FontCache",
    "gpsvc", "LanmanServer", "LanmanWorkstation", "Lsm", "Netlogon",
    "PlugPlay", "Power", "RpcEptMapper", "RpcSs", "SamSs",
    "Schedule", "SENS", "ShellHWDetection", "Spooler", "srservice",
    "TermService", "Themes", "TrkWks", "UserManager", "W32Time",
    "WinDefend", "WinHttpAutoProxySvc", "Winmgmt", "WlanSvc",
    "wuauserv", "WSearch", "SysMain", "ClipSVC", "CoreMessagingRegistrar",
}

# 备份目录
BACKUP_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
    "workspace", "forensics_backups",
)


def _get_backup_dir():
    os.makedirs(BACKUP_DIR, exist_ok=True)
    return BACKUP_DIR


def _remove_registry_startup(identifier: str, action_id: str) -> dict:
    """删除注册表启动项并导出备份。"""
    # 导出备份
    backup_path = os.path.join(_get_backup_dir(), f"{action_id}.reg")
    export_cmd = f"reg export \"{identifier}\" \"{backup_path}\" /y"
    run_powershell(export_cmd, timeout=10)

    # 从 identifier 中分离路径和键名
    # identifier 格式: "HKCU\Software\Microsoft\Windows\CurrentVersion\Run\WindowsUpdate"
    parts = identifier.rsplit("\\", 1)
    if len(parts) == 2:
        reg_path, key_name = parts
    else:
        reg_path = identifier
        key_name = ""

    # 转换为 PowerShell 注册表路径
    # HKLM: -> HKLM:\, HKCU: -> HKCU:\
    ps_path = reg_path.replace("HKLM", "HKLM:").replace("HKCU", "HKCU:").replace("HKCR", "HKCR:")

    # 删除键值
    if key_name:
        cmd = (
            f"Remove-ItemProperty -Path '{ps_path}' -Name '{key_name}' "
            f"-ErrorAction Stop"
        )
    else:
        cmd = f"Remove-Item -Path '{ps_path}' -ErrorAction Stop"

    r = run_powershell(cmd, timeout=15)
    return {
        "type": "registry",
        "identifier": identifier,
        "success": r["success"],
        "output": r["stdout"] if r["success"] else (r["error"] or r["stderr"]),
        "backup": backup_path,
    }


def _remove_task_startup(identifier: str, action_id: str) -> dict:
    """删除计划任务并导出备份。"""
    # 导出任务 XML 备份
    backup_path = os.path.join(_get_backup_dir(), f"{action_id}.xml")
    export_cmd = f"schtasks /query /tn \"{identifier}\" /xml > \"{backup_path}\""
    run_powershell(export_cmd, timeout=10)

    # 删除任务
    cmd = f"schtasks /delete /tn \"{identifier}\" /f"
    r = run_powershell(cmd, timeout=15)
    return {
        "type": "scheduled_task",
        "identifier": identifier,
        "success": r["success"],
        "output": r["stdout"] if r["success"] else (r["error"] or r["stderr"]),
        "backup": backup_path,
    }


def _remove_service_startup(identifier: str, action_id: str) -> dict:
    """禁用并停止服务，导出备份。"""
    # 检查白名单
    for protected in PROTECTED_SERVICES:
        if identifier.lower() == protected.lower():
            return {
                "type": "service",
                "identifier": identifier,
                "success": False,
                "output": f"系统保护服务，禁止操作: {identifier}",
                "backup": "",
            }

    # 导出服务配置备份
    backup_path = os.path.join(_get_backup_dir(), f"{action_id}_svc.txt")
    export_cmd = (
        f"sc qc \"{identifier}\" > \"{backup_path}\" 2>&1; "
        f"sc qdescription \"{identifier}\" >> \"{backup_path}\" 2>&1"
    )
    run_powershell(export_cmd, timeout=10)

    # 停止并禁用服务
    stop_cmd = f"sc stop \"{identifier}\""
    disable_cmd = f"sc config \"{identifier}\" start= disabled"

    stop_r = run_powershell(stop_cmd, timeout=30)
    disable_r = run_powershell(disable_cmd, timeout=10)

    success = stop_r["success"] or "STOP_PENDING" in stop_r["stdout"]
    return {
        "type": "service",
        "identifier": identifier,
        "success": success,
        "output": f"stop: {stop_r['stdout']}, disable: {disable_r['stdout']}",
        "backup": backup_path,
    }


@tool("remove_startup", parse_docstring=True)
def remove_startup(
    source: str,
    identifier: str,
) -> str:
    """删除恶意启动项。

    支持三种启动项类型：注册表 Run 键、计划任务、Windows 服务。
    操作前自动导出备份，支持回滚。

    Args:
        source: 启动项类型，"registry"（注册表）/ "task"（计划任务）/ "service"（服务）。
        identifier: 启动项标识符。registry 格式为注册表完整路径（如 HKCU\\Software\\...\\Run\\ItemName），
            task 格式为计划任务名称（如 \\Microsoft\\Windows\\UpdateTask），
            service 格式为服务名称（如 wuauserv）。

    Returns:
        JSON 字符串，包含操作结果和备份信息。
    """
    valid_sources = ["registry", "task", "service"]
    if source not in valid_sources:
        return format_result(
            False,
            error=f"无效的 source 参数: {source}，可选值: {', '.join(valid_sources)}",
        )

    action_id = f"rmstartup_{source}_{int(time.time())}"
    timestamp = datetime.now().isoformat()

    # 保存操作元数据
    metadata = {
        "action": "remove_startup",
        "action_id": action_id,
        "source": source,
        "identifier": identifier,
        "timestamp": timestamp,
    }

    # 执行对应操作
    if source == "registry":
        result = _remove_registry_startup(identifier, action_id)
    elif source == "task":
        result = _remove_task_startup(identifier, action_id)
    else:  # service
        result = _remove_service_startup(identifier, action_id)

    # 合并结果
    full_result = {**metadata, **result}

    # 保存备份记录
    backup_record_path = os.path.join(_get_backup_dir(), f"{action_id}.json")
    try:
        with open(backup_record_path, "w", encoding="utf-8") as f:
            json.dump(full_result, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning(f"备份记录保存失败: {e}")

    return format_result(
        success=result["success"],
        data=full_result,
        error=None if result["success"] else result.get("output"),
    )
