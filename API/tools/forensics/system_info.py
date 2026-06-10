"""
系统信息采集工具 (v4.0)

采集主机基本信息：OS版本、用户、防火墙、杀软状态等。
风险等级：Level 0（纯信息采集，无安全风险）

注意：此机器 WMI/CIM 子系统不可用，全部使用注册表/Python 原生方式。
"""

from __future__ import annotations

import json
import logging
import os as _os
import platform
import socket as _socket

from langchain_core.tools import tool

from ._utils import run_powershell, format_result

logger = logging.getLogger(__name__)

CMD_TIMEOUT = 5  # 短超时，避免 WMI 卡死


@tool("collect_system_info", parse_docstring=True)
def collect_system_info() -> str:
    """采集主机系统基本信息，为安全调查提供上下文。

    Returns:
        JSON 字符串，包含系统各项信息。
    """
    info = {}
    errors = []

    # 1. OS 版本 — Python platform 模块（最快，不依赖任何外部命令）
    try:
        info["os"] = {
            "system": platform.system(),
            "release": platform.release(),
            "version": platform.version(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "hostname": _socket.gethostname(),
            "python_version": platform.python_version(),
        }
    except Exception as e:
        errors.append(f"OS信息采集失败: {e}")

    # 2. OS 详细信息 — 注册表直读（不依赖 WMI）
    r = run_powershell(
        'Get-ItemProperty "HKLM:\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion" 2>$null | '
        'Select-Object ProductName,DisplayVersion,CurrentBuild,UBR,InstallDate,RegisteredOwner | '
        'ConvertTo-Json',
        timeout=CMD_TIMEOUT,
    )
    if r["success"] and r["stdout"]:
        try:
            info["os_details"] = json.loads(r["stdout"])
        except json.JSONDecodeError:
            info["os_details"] = r["stdout"][:300]
    else:
        errors.append(f"OS详情采集失败（WMI可能不可用）")

    # 3. 用户信息 — net user（不依赖 WMI）
    r = run_powershell("net user 2>&1", timeout=CMD_TIMEOUT)
    if r["success"]:
        info["users"] = r["stdout"][:1000]
    else:
        errors.append(f"用户列表采集失败")

    r = run_powershell("net localgroup Administrators 2>&1", timeout=CMD_TIMEOUT)
    if r["success"]:
        info["administrators"] = r["stdout"][:800]
    else:
        errors.append(f"管理员组采集失败")

    # 4. 防火墙 — netsh（不依赖 WMI）
    r = run_powershell("netsh advfirewall show allprofiles state 2>&1", timeout=CMD_TIMEOUT)
    if r["success"]:
        info["firewall"] = r["stdout"][:800]

    # 5. 网络连接 — netstat（不依赖 WMI）
    r = run_powershell("netstat -ano 2>&1 | Select-Object -First 50", timeout=CMD_TIMEOUT)
    if r["success"]:
        info["network_connections"] = r["stdout"][:2000]

    # 6. 系统环境
    info["environment"] = {
        "path": _os.environ.get("PATH", "")[:500],
        "username": _os.environ.get("USERNAME", ""),
        "computername": _os.environ.get("COMPUTERNAME", ""),
        "tmp": _os.environ.get("TEMP", "")[:200],
    }

    # 7. 杀软 — 尝试 Get-MpComputerStatus（测试是否可用）
    r = run_powershell(
        "Get-MpComputerStatus 2>$null | "
        "Select-Object AntivirusEnabled,RealTimeProtectionEnabled | ConvertTo-Json",
        timeout=CMD_TIMEOUT,
    )
    if r["success"] and r["stdout"]:
        try:
            info["defender"] = json.loads(r["stdout"])
        except json.JSONDecodeError:
            info["defender"] = {"raw": r["stdout"][:200]}

    if errors:
        info["_errors"] = errors

    return format_result(
        success=True,
        data=info,
        error="; ".join(errors) if errors else None,
    )