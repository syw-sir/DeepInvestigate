"""
进程枚举与分析工具 (v4.0)

枚举所有运行中进程，提取关键信息并识别可疑进程。
风险等级：Level 1（读取进程信息，不修改）
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
    """检测进程名是否伪装系统进程（如 svch0st.exe 伪装 svchost.exe）"""
    name_lower = name.lower()
    for sys_name in SYSTEM_PROCESS_NAMES:
        sys_lower = sys_name.lower()
        if name_lower == sys_lower:
            return False  # 就是系统进程本身
        # 检查是否是轻微变体（替换/插入/删除字符）
        if len(name_lower) == len(sys_lower):
            diff_count = sum(1 for a, b in zip(name_lower, sys_lower) if a != b)
            if diff_count <= 2:
                return True
    return False


def _check_suspicious(proc: dict) -> dict:
    """对单个进程进行可疑度分析，返回风险标记。"""
    flags = []
    path = (proc.get("Path") or "").lower()
    name = (proc.get("ProcessName") or "").lower()
    cmdline = (proc.get("CommandLine") or "")

    # 1. 路径在临时目录
    for sp in SUSPICIOUS_PATHS:
        if re.search(sp, path):
            flags.append(f"临时目录执行: {path}")
            break

    # 2. 无数字签名
    company = proc.get("Company")
    if not company or company in ("", "Unknown"):
        flags.append("无数字签名")

    # 3. 名称伪装系统进程
    if _is_name_masquerading(name.replace(".exe", "")):
        flags.append(f"进程名疑似伪装: {name}")

    # 4. 命令行包含可疑特征
    cmd_lower = cmdline.lower()
    for keyword in SUSPICIOUS_CMD_KEYWORDS:
        if keyword.lower() in cmd_lower:
            flags.append(f"可疑命令行: {keyword}")
            break

    # 5. 父进程可疑（由 Investigator 在分析时结合上下文判断，这里仅标记）
    parent_name = (proc.get("ParentProcessName") or "").lower()
    if parent_name in [p.lower() for p in SUSPICIOUS_PARENTS]:
        flags.append(f"可疑父进程: {parent_name}")

    return {
        "suspicious": len(flags) > 0,
        "suspicion_level": min(len(flags), 3),  # 0-3
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
    ps_cmd = (
        "Get-CimInstance Win32_Process | "
        "Select-Object ProcessId,Name,ProcessName,Path,CommandLine,"
        "ParentProcessId,Handle,WorkingSetSize,ThreadCount,"
        "CreationDate,ExecutablePath | ConvertTo-Json -Depth 2"
    )

    r = run_powershell(ps_cmd, timeout=120)
    if not r["success"]:
        return format_result(False, error=r["error"] or r["stderr"])

    raw_processes = safe_json_parse(r["stdout"])
    if isinstance(raw_processes, dict) and not raw_processes.get("parse_error"):
        raw_processes = [raw_processes]
    if not isinstance(raw_processes, list):
        return format_result(False, error="进程数据解析失败")

    # 后处理：增强进程信息 + 可疑分析
    processes = []
    for proc in raw_processes:
        pid = proc.get("ProcessId")
        if pid is None:
            continue

        # 尝试获取更详细的信息（签名、父进程名）
        name = proc.get("Name") or proc.get("ProcessName") or ""

        if filter_name and filter_name.lower() not in name.lower():
            continue

        # 获取父进程名
        ppid = proc.get("ParentProcessId")
        parent_name = ""
        if ppid:
            ps_parent = (
                f"Get-Process -Id {ppid} -ErrorAction SilentlyContinue | "
                "Select-Object -ExpandProperty ProcessName"
            )
            pr = run_powershell(ps_parent, timeout=10)
            if pr["success"] and pr["stdout"]:
                parent_name = pr["stdout"].strip()

        # 获取文件签名信息
        exe_path = proc.get("ExecutablePath") or proc.get("Path") or ""
        company = ""
        if exe_path:
            ps_sig = (
                f"Get-AuthenticodeSignature -FilePath '{exe_path}' "
                "-ErrorAction SilentlyContinue | "
                "Select-Object -ExpandProperty SignerCertificate | "
                "Select-Object -ExpandProperty Subject"
            )
            sr = run_powershell(ps_sig, timeout=15)
            if sr["success"] and sr["stdout"]:
                # 从 Subject 中提取 CN=xxx
                cn_match = re.search(r"CN=([^,]+)", sr["stdout"])
                company = cn_match.group(1) if cn_match else sr["stdout"].strip()[:80]

        enhanced = {
            "pid": pid,
            "name": name,
            "path": exe_path,
            "command_line": proc.get("CommandLine") or "",
            "parent_pid": ppid,
            "parent_name": parent_name,
            "company": company,
            "user": "",  # Get-CimInstance Win32_Process 不直接提供用户
            "cpu": None,
            "memory_mb": round((proc.get("WorkingSetSize") or 0) / (1024 * 1024), 2),
            "threads": proc.get("ThreadCount"),
            "created": str(proc.get("CreationDate") or ""),
        }

        # 可疑分析
        suspicion = _check_suspicious(enhanced)
        enhanced.update(suspicion)

        if suspicious_only and not suspicion["suspicious"]:
            continue

        processes.append(enhanced)

    # 统计
    total = len(processes)
    suspicious_count = sum(1 for p in processes if p.get("suspicious"))

    return format_result(
        success=True,
        data={
            "total_processes": total,
            "suspicious_count": suspicious_count,
            "filter_name": filter_name,
            "suspicious_only": suspicious_only,
            "processes": processes,
        },
    )