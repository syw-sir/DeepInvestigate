"""
进程枚举与分析工具 (v4.0)

枚举所有运行中进程，提取关键信息并识别可疑进程。
风险等级：Level 1（读取进程信息，不修改）

注意：此机器 WMI/CIM 可能卡死，使用 Get-Process 代替 Get-CimInstance。
"""

from __future__ import annotations

import json
import logging
import re
from typing import Optional

from langchain_core.tools import tool

from ._utils import run_powershell, safe_json_parse, format_result

logger = logging.getLogger(__name__)

# 可疑路径特征
SUSPICIOUS_PATHS = [
    r"(?i)\\Temp\\",
    r"(?i)\\AppData\\Local\\Temp\\",
    r"(?i)\\Users\\Public\\",
    r"(?i)\\ProgramData\\Temp\\",
    r"(?i)\\Downloads\\",
    r"(?i)\\Temporary Internet Files\\",
]

# 可疑父进程
SUSPICIOUS_PARENTS = [
    "winword.exe", "excel.exe", "powerpnt.exe", "outlook.exe",
    "wscript.exe", "cscript.exe", "mshta.exe", "msiexec.exe",
    "regsvr32.exe", "rundll32.exe",
]

# 命令行可疑特征
SUSPICIOUS_CMD_KEYWORDS = [
    "-enc", "-EncodedCommand", "-e ",
    "IEX", "Invoke-Expression",
    "Invoke-WebRequest", "Invoke-RestMethod",
    "DownloadString", "DownloadFile",
    "FromBase64String", "ToBase64String",
    "Net.WebClient", "Net.Sockets",
    "Start-Process -WindowStyle Hidden",
    "New-Object System.Net",
    "iex(", "iex (",
]

# 系统进程名伪装检测
SYSTEM_PROCESS_NAMES = {
    "svchost.exe", "lsass.exe", "csrss.exe", "smss.exe",
    "winlogon.exe", "services.exe", "spoolsv.exe", "taskhostw.exe",
    "wininit.exe", "dwm.exe", "explorer.exe",
}


def _is_name_masquerading(name: str) -> bool:
    """检测进程名是否伪装系统进程"""
    name_lower = name.lower()
    for sys_name in SYSTEM_PROCESS_NAMES:
        sys_lower = sys_name.lower()
        if name_lower == sys_lower:
            return False
        if len(name_lower) == len(sys_lower):
            diff_count = sum(1 for a, b in zip(name_lower, sys_lower) if a != b)
            if diff_count <= 2:
                return True
    return False


def _check_suspicious(proc: dict) -> dict:
    """对单个进程进行可疑度分析"""
    flags = []
    path = (proc.get("path") or "").lower()
    name = (proc.get("name") or "").lower()

    # 1. 路径在临时目录
    for sp in SUSPICIOUS_PATHS:
        if re.search(sp, path):
            flags.append(f"临时目录执行: {path}")
            break

    # 2. 名称伪装
    if _is_name_masquerading(name.replace(".exe", "")):
        flags.append(f"进程名疑似伪装: {name}")

    # 3. 可疑父进程
    parent_name = (proc.get("parent_name") or "").lower()
    if parent_name in [p.lower() for p in SUSPICIOUS_PARENTS]:
        flags.append(f"可疑父进程: {parent_name}")

    return {
        "suspicious": len(flags) > 0,
        "suspicion_level": min(len(flags), 3),
        "flags": flags,
    }


@tool("scan_processes", parse_docstring=True)
def scan_processes(
    filter_name: Optional[str] = None,
    suspicious_only: bool = False,
) -> str:
    """枚举系统中所有运行进程，提取关键信息并标记可疑进程。

    Args:
        filter_name: 可选，按进程名过滤（模糊匹配）。
        suspicious_only: 是否仅返回标记为可疑的进程，默认 False 返回全部。

    Returns:
        JSON 字符串，包含进程列表和可疑分析结果。
    """
    # 使用 Get-Process（不依赖 CIM/WMI），一次调用获取所有进程
    # 注意：-IncludeUserName 需要管理员权限，去掉以保证非管理员也能运行
    ps_cmd = (
        "Get-Process | "
        "Select-Object Id,ProcessName,Path,Company,CPU,"
        "WorkingSet64,StartTime | "
        "Sort-Object WorkingSet64 -Descending | "
        "ConvertTo-Json -Depth 1"
    )

    r = run_powershell(ps_cmd, timeout=30)
    if not r["success"]:
        return format_result(False, error=r["error"] or r["stderr"])

    raw = safe_json_parse(r["stdout"])
    if isinstance(raw, dict) and not raw.get("parse_error"):
        raw = [raw]
    if not isinstance(raw, list):
        return format_result(False, error="进程数据解析失败")

    processes = []
    for p in raw:
        pid = p.get("Id")
        if pid is None:
            continue

        name = p.get("ProcessName") or ""
        if filter_name and filter_name.lower() not in name.lower():
            continue

        path = p.get("Path") or ""
        ws = p.get("WorkingSet64") or 0

        proc = {
            "pid": pid,
            "name": name,
            "path": path,
            "user": p.get("UserName") or "",
            "company": p.get("Company") or "",
            "cpu": p.get("CPU"),
            "memory_mb": round(ws / (1024 * 1024), 2) if ws else 0,
            "start_time": str(p.get("StartTime") or ""),
        }
        # 注意：非管理员时 Get-Process 不返回 UserName，user 字段可能为空。
        # 如需进程用户信息，可单独使用 tasklist /V 获取。

        # 快速可疑分析（不调用额外 PowerShell）
        suspicion = _check_suspicious(proc)
        proc.update(suspicion)

        if suspicious_only and not suspicion["suspicious"]:
            continue

        processes.append(proc)

    suspicious_count = sum(1 for p in processes if p.get("suspicious"))

    return format_result(
        success=True,
        data={
            "total_processes": len(processes),
            "suspicious_count": suspicious_count,
            "filter_name": filter_name,
            "suspicious_only": suspicious_only,
            "processes": processes,
        },
    )