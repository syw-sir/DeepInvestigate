"""
启动项/计划任务检查工具 (v4.0)

检查系统启动项和计划任务，发现持久化后门。
风险等级：Level 1（读取注册表/任务信息，不修改）
"""

from __future__ import annotations

import json
import logging
import re
from typing import Optional

from langchain_core.tools import tool

from ._utils import run_powershell, safe_json_parse, format_result

logger = logging.getLogger(__name__)


def _check_suspicious_startup(item: dict) -> dict:
    """检查单个启动项是否可疑。"""
    flags = []
    command = (item.get("command") or item.get("task_to_run") or "").lower()
    name = (item.get("name") or item.get("task_name") or "").lower()

    # 1. 路径在临时目录
    suspicious_dirs = ["\\temp\\", "\\appdata\\local\\temp\\", "\\users\\public\\", "\\downloads\\"]
    for sd in suspicious_dirs:
        if sd in command:
            flags.append(f"临时目录路径: {sd}")
            break

    # 2. 命令行包含可疑特征
    suspicious_cmds = ["-enc", "-encodedcommand", "iex", "invoke-expression",
                       "invoke-webrequest", "downloadstring", "frombase64string",
                       "net.webclient", "-windowstyle hidden"]
    for sc in suspicious_cmds:
        if sc in command:
            flags.append(f"可疑命令: {sc}")
            break

    # 3. 无签名（如果提供了签名信息）
    signed = item.get("signed", True)
    if not signed and command:
        flags.append("无数字签名")

    # 4. 计划任务触发器异常（高频执行）
    trigger = (item.get("trigger") or "").lower()
    if "hourly" in trigger or "at log on" in trigger or "at startup" in trigger:
        # 正常，但结合其他指标则可疑
        pass

    return {
        "suspicious": len(flags) > 0,
        "flags": flags,
    }


@tool("check_startup", parse_docstring=True)
def check_startup(
    scope: str = "all",
) -> str:
    """检查系统启动项和计划任务，发现潜在的持久化后门。

    检查范围包括：注册表Run键、计划任务、启动文件夹、非Microsoft自动启动服务。

    Args:
        scope: 检查范围，可选 "registry" / "tasks" / "services" / "all"，默认 "all"。

    Returns:
        JSON 字符串，按类别分组的启动项列表和可疑分析。
    """
    results = {}
    errors = []

    # ---- 1. 注册表 Run 键 ----
    if scope in ("registry", "all"):
        registry_keys = [
            "HKLM:\\Software\\Microsoft\\Windows\\CurrentVersion\\Run",
            "HKLM:\\Software\\Microsoft\\Windows\\CurrentVersion\\RunOnce",
            "HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Run",
            "HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\RunOnce",
        ]
        run_items = []
        for rk in registry_keys:
            ps_reg = (
                f"Get-ItemProperty -Path 'Registry::{rk}' -ErrorAction SilentlyContinue | "
                "Select-Object -Property * -ExcludeProperty PS* | ConvertTo-Json"
            )
            r = run_powershell(ps_reg, timeout=30)
            if r["success"] and r["stdout"]:
                props = safe_json_parse(r["stdout"])
                if isinstance(props, dict) and not props.get("parse_error"):
                    for key, value in props.items():
                        if key not in ("PSPath", "PSParentPath", "PSChildName", "PSDrive", "PSProvider"):
                            item = {
                                "source": rk,
                                "name": key,
                                "command": str(value),
                            }
                            item.update(_check_suspicious_startup(item))
                            run_items.append(item)

        results["registry_run"] = {
            "count": len(run_items),
            "items": run_items,
        }

    # ---- 2. 计划任务 ----
    if scope in ("tasks", "all"):
        ps_tasks = (
            "Get-ScheduledTask | Where-Object {$_.State -ne 'Disabled'} | "
            "Select-Object TaskName,TaskPath,State,"
            "@{Name='Trigger';Expression={($_.Triggers | ForEach-Object {$_.ToString()}) -join '; '}},"
            "@{Name='Action';Expression={($_.Actions | ForEach-Object {$_.Execute + ' ' + $_.Arguments}) -join '; '}} | "
            "ConvertTo-Json -Depth 2"
        )
        r = run_powershell(ps_tasks, timeout=60)
        task_items = []
        if r["success"]:
            tasks = safe_json_parse(r["stdout"])
            if isinstance(tasks, dict) and not tasks.get("parse_error"):
                tasks = [tasks]
            if isinstance(tasks, list):
                for t in tasks:
                    item = {
                        "name": t.get("TaskName", ""),
                        "path": t.get("TaskPath", ""),
                        "state": t.get("State", ""),
                        "trigger": t.get("Trigger", ""),
                        "command": t.get("Action", ""),
                    }
                    item.update(_check_suspicious_startup(item))
                    task_items.append(item)
        else:
            errors.append(f"计划任务查询失败: {r['error'] or r['stderr']}")

        results["scheduled_tasks"] = {
            "count": len(task_items),
            "items": task_items,
        }

    # ---- 3. 自动启动服务（非 Microsoft） ----
    if scope in ("services", "all"):
        # 使用 Get-Service + WMI 的注册表查询代替 CIM（避免 WMI 卡死）
        ps_svc = (
            "Get-Service | Where-Object {"
            "$_.StartType -eq 'Automatic' -and $_.BinaryPathName -ne $null -and "
            "$_.BinaryPathName -notlike '*Microsoft*' -and $_.BinaryPathName -notlike '*Windows*'"
            "} | Select-Object Name,DisplayName,BinaryPathName,StartType,Status | "
            "ConvertTo-Json -Depth 1"
        )
        r = run_powershell(ps_svc, timeout=15)
        svc_items = []
        if r["success"]:
            svcs = safe_json_parse(r["stdout"])
            if isinstance(svcs, dict) and not svcs.get("parse_error"):
                svcs = [svcs]
            if isinstance(svcs, list):
                for s in svcs:
                    # Get-Service 字段名不同于 Get-CimInstance
                    path = s.get("BinaryPathName") or s.get("PathName", "")
                    item = {
                        "name": s.get("Name", ""),
                        "display_name": s.get("DisplayName", ""),
                        "command": path,
                        "account": s.get("StartName") or s.get("StartType", ""),
                        "state": s.get("Status") or s.get("State", ""),
                    }
                    item.update(_check_suspicious_startup(item))
                    svc_items.append(item)
        else:
            errors.append(f"服务查询失败: {r['error'] or r['stderr']}")

        results["auto_start_services"] = {
            "count": len(svc_items),
            "items": svc_items,
        }

    # ---- 4. 启动文件夹 ----
    if scope in ("all",):
        startup_folders = [
            "$env:APPDATA + '\\Microsoft\\Windows\\Start Menu\\Programs\\Startup'",
            "$env:PROGRAMDATA + '\\Microsoft\\Windows\\Start Menu\\Programs\\Startup'",
        ]
        folder_items = []
        for sf in startup_folders:
            ps_folder = (
                f"Get-ChildItem -Path ({sf}) -ErrorAction SilentlyContinue | "
                "Select-Object Name,FullName,LastWriteTime | ConvertTo-Json"
            )
            r = run_powershell(ps_folder, timeout=30)
            if r["success"] and r["stdout"]:
                files = safe_json_parse(r["stdout"])
                if isinstance(files, dict) and not files.get("parse_error"):
                    files = [files]
                if isinstance(files, list):
                    for f in files:
                        item = {
                            "name": f.get("Name", ""),
                            "path": f.get("FullName", ""),
                            "modified": str(f.get("LastWriteTime", "")),
                            "type": "startup_folder",
                        }
                        item.update(_check_suspicious_startup(item))
                        folder_items.append(item)

        results["startup_folders"] = {
            "count": len(folder_items),
            "items": folder_items,
        }

    # 汇总统计
    total_items = sum(
        len(results.get(k, {}).get("items", []))
        for k in results
    )
    total_suspicious = sum(
        sum(1 for item in results.get(k, {}).get("items", []) if item.get("suspicious"))
        for k in results
    )

    return format_result(
        success=len(errors) < 2,
        data={
            "total_items": total_items,
            "suspicious_count": total_suspicious,
            "scope": scope,
            **results,
        },
        error="; ".join(errors) if errors else None,
    )