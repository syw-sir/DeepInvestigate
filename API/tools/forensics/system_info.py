"""
系统信息采集工具 (v4.0)

采集主机基本信息：OS版本、补丁、用户、防火墙、杀软状态等。
风险等级：Level 0（纯信息采集，无安全风险）
"""

from __future__ import annotations

import json
import logging

from langchain_core.tools import tool

from ._utils import run_powershell, safe_json_parse, format_result

logger = logging.getLogger(__name__)


@tool("collect_system_info", parse_docstring=True)
def collect_system_info() -> str:
    """采集主机系统基本信息，为安全调查提供上下文。

    采集内容包括：OS版本与Build号、最近安装的补丁、本地用户列表、
    管理员组成员、防火墙状态、杀软状态、系统环境变量。

    Returns:
        JSON 字符串，包含系统各项信息。
    """
    info = {}
    errors = []

    # 1. OS 版本信息
    ps_os = (
        "Get-CimInstance Win32_OperatingSystem | "
        "Select-Object Caption,Version,BuildNumber,OSArchitecture,LastBootUpTime,"
        "InstallDate,RegisteredUser | ConvertTo-Json"
    )
    r = run_powershell(ps_os)
    if r["success"]:
        info["os"] = safe_json_parse(r["stdout"])
    else:
        errors.append(f"OS信息采集失败: {r['error'] or r['stderr']}")

    # 2. 最近安装的补丁（最近 10 个）
    ps_hotfix = (
        "Get-HotFix | Sort-Object InstalledOn -Descending | Select-Object -First 10 "
        "HotFixID,Description,InstalledOn,InstalledBy | ConvertTo-Json"
    )
    r = run_powershell(ps_hotfix)
    if r["success"]:
        hotfixes = safe_json_parse(r["stdout"])
        if isinstance(hotfixes, dict) and not hotfixes.get("parse_error"):
            hotfixes = [hotfixes]  # 单条记录转为列表
        info["recent_hotfixes"] = hotfixes if isinstance(hotfixes, list) else []
    else:
        errors.append(f"补丁信息采集失败: {r['error'] or r['stderr']}")

    # 3. 本地用户列表
    ps_users = (
        "Get-LocalUser | Select-Object Name,Enabled,LastLogon,Description | ConvertTo-Json"
    )
    r = run_powershell(ps_users)
    if r["success"]:
        users = safe_json_parse(r["stdout"])
        if isinstance(users, dict) and not users.get("parse_error"):
            users = [users]
        info["local_users"] = users if isinstance(users, list) else []
    else:
        errors.append(f"用户列表采集失败: {r['error'] or r['stderr']}")

    # 4. 管理员组成员
    ps_admins = (
        "Get-LocalGroupMember -Group 'Administrators' | "
        "Select-Object Name,ObjectClass,PrincipalSource | ConvertTo-Json"
    )
    r = run_powershell(ps_admins)
    if r["success"]:
        admins = safe_json_parse(r["stdout"])
        if isinstance(admins, dict) and not admins.get("parse_error"):
            admins = [admins]
        info["administrators"] = admins if isinstance(admins, list) else []
    else:
        errors.append(f"管理员组采集失败: {r['error'] or r['stderr']}")

    # 5. 防火墙状态
    ps_fw = (
        "Get-NetFirewallProfile | Select-Object Name,Enabled | ConvertTo-Json"
    )
    r = run_powershell(ps_fw)
    if r["success"]:
        fw = safe_json_parse(r["stdout"])
        if isinstance(fw, dict) and not fw.get("parse_error"):
            fw = [fw]
        info["firewall_profiles"] = fw if isinstance(fw, list) else []
    else:
        errors.append(f"防火墙状态采集失败: {r['error'] or r['stderr']}")

    # 6. 杀软状态
    ps_av = (
        "Get-CimInstance -Namespace root/SecurityCenter2 -ClassName AntivirusProduct | "
        "Select-Object displayName,productState | ConvertTo-Json"
    )
    r = run_powershell(ps_av)
    if r["success"]:
        av = safe_json_parse(r["stdout"])
        if isinstance(av, dict) and not av.get("parse_error"):
            av = [av]
        info["antivirus"] = av if isinstance(av, list) else []
    else:
        # 尝试 Windows Defender 专属命令
        ps_defender = "Get-MpComputerStatus | Select-Object AntivirusEnabled,RealTimeProtectionEnabled,AntivirusSignatureLastUpdated | ConvertTo-Json"
        r2 = run_powershell(ps_defender)
        if r2["success"]:
            info["antivirus"] = [safe_json_parse(r2["stdout"])]
        else:
            errors.append(f"杀软状态采集失败: {r['error'] or r['stderr']}")

    # 7. 环境变量 PATH
    ps_env = "$env:PATH"
    r = run_powershell(ps_env)
    if r["success"]:
        info["path_environment"] = r["stdout"]
    else:
        errors.append(f"环境变量采集失败: {r['error'] or r['stderr']}")

    if errors:
        info["_errors"] = errors

    return format_result(
        success=len(errors) < 3,  # 少量错误仍算成功
        data=info,
        error="; ".join(errors) if errors else None,
    )