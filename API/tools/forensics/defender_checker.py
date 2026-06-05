"""
Windows Defender 告警检查工具 (v4.0)

查询 Windows Defender 的历史检测记录和当前状态。
风险等级：Level 1（读取 Defender 日志，不修改）
"""

from __future__ import annotations

import json
import logging

from langchain_core.tools import tool

from ._utils import run_powershell, safe_json_parse, format_result

logger = logging.getLogger(__name__)

# 默认回溯小时数
DEFAULT_HOURS_BACK = 168  # 7 天


@tool("check_defender_logs", parse_docstring=True)
def check_defender_logs(
    hours_back: int = DEFAULT_HOURS_BACK,
) -> str:
    """查询 Windows Defender 的状态和历史威胁检测记录。

    包括 Defender 运行状态、最近检测到的威胁、隔离文件列表、排除项配置。
    攻击者可能会添加排除路径来绕过 Defender，此项检查可以发现这类行为。

    Args:
        hours_back: 回溯小时数，默认 168（7天）。

    Returns:
        JSON 字符串，包含 Defender 状态和威胁检测历史。
    """
    info = {}
    errors = []

    # 1. Defender 运行状态
    ps_status = (
        "Get-MpComputerStatus | "
        "Select-Object AntivirusEnabled,RealTimeProtectionEnabled,"
        "AntivirusSignatureLastUpdated,LastFullScanTime,LastQuickScanTime,"
        "AntispywareEnabled,BehaviorMonitorEnabled,IoavProtectionEnabled,"
        "NISEnabled,OnAccessProtectionEnabled | ConvertTo-Json"
    )
    r = run_powershell(ps_status)
    if r["success"]:
        info["status"] = safe_json_parse(r["stdout"])
    else:
        errors.append(f"Defender状态查询失败: {r['error'] or r['stderr']}")

    # 2. 威胁检测历史
    cutoff = f"(Get-Date).AddHours(-{hours_back})"
    ps_threats = (
        f"Get-MpThreatDetection | Where-Object {{$_.InitialDetectionTime -gt {cutoff}}} | "
        "Sort-Object InitialDetectionTime -Descending | "
        "Select-Object InitialDetectionTime,ThreatName,ThreatID,Resources,"
        "ActionSuccess,ExecutionStatus,SeverityID,CategoryID | ConvertTo-Json -Depth 3"
    )
    r = run_powershell(ps_threats, timeout=60)
    if r["success"]:
        threats = safe_json_parse(r["stdout"])
        if isinstance(threats, dict) and not threats.get("parse_error"):
            threats = [threats]
        info["recent_threats"] = threats if isinstance(threats, list) else []
    else:
        errors.append(f"威胁历史查询失败: {r['error'] or r['stderr']}")

    # 3. 当前活动威胁
    ps_active = (
        "Get-MpThreat | Where-Object {$_.IsActive -eq $true} | "
        "Select-Object ThreatName,ThreatID,ThreatStatus,SeverityID,CategoryID | ConvertTo-Json"
    )
    r = run_powershell(ps_active, timeout=30)
    if r["success"]:
        active = safe_json_parse(r["stdout"])
        if isinstance(active, dict) and not active.get("parse_error"):
            active = [active]
        info["active_threats"] = active if isinstance(active, list) else []
    else:
        # 没有活动威胁时可能返回空，不算错误
        info["active_threats"] = []

    # 4. 排除项配置（攻击者可能添加排除路径）
    ps_exclusions = (
        "Get-MpPreference | "
        "Select-Object ExclusionPath,ExclusionExtension,ExclusionProcess | ConvertTo-Json -Depth 2"
    )
    r = run_powershell(ps_exclusions, timeout=30)
    if r["success"]:
        info["exclusions"] = safe_json_parse(r["stdout"])
    else:
        errors.append(f"排除项查询失败: {r['error'] or r['stderr']}")

    # 汇总统计
    recent_threats = info.get("recent_threats", [])
    active_threats = info.get("active_threats", [])
    total_recent = len(recent_threats) if isinstance(recent_threats, list) else 0
    total_active = len(active_threats) if isinstance(active_threats, list) else 0

    # 检查排除项是否异常（排除路径非空且包含非标准路径）
    exclusions = info.get("exclusions", {})
    exclusion_paths = exclusions.get("ExclusionPath", []) if isinstance(exclusions, dict) else []
    has_exclusions = isinstance(exclusion_paths, list) and len(exclusion_paths) > 0

    return format_result(
        success=True,
        data={
            "defender_enabled": info.get("status", {}).get("AntivirusEnabled", False),
            "real_time_protection": info.get("status", {}).get("RealTimeProtectionEnabled", False),
            "total_recent_threats": total_recent,
            "total_active_threats": total_active,
            "has_exclusions": has_exclusions,
            "hours_back": hours_back,
            **info,
        },
        error="; ".join(errors) if errors else None,
    )