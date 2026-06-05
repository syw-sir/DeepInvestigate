"""
注册表可疑项扫描工具 (v4.0)

扫描注册表中的常见恶意软件驻留位置和持久化机制。
风险等级：Level 2（读取敏感注册表位置）
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from langchain_core.tools import tool

from ._utils import run_powershell, safe_json_parse, format_result

logger = logging.getLogger(__name__)

# 扫描位置定义
SCAN_LOCATIONS = {
    "persistence": [
        {
            "path": "HKLM:\\Software\\Microsoft\\Windows\\CurrentVersion\\Run",
            "description": "系统级启动项",
            "technique": "T1547.001",
        },
        {
            "path": "HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Run",
            "description": "用户级启动项",
            "technique": "T1547.001",
        },
        {
            "path": "HKLM:\\Software\\Microsoft\\Windows NT\\CurrentVersion\\Winlogon",
            "description": "Winlogon 劫持（Shell/Userinit）",
            "technique": "T1547.004",
        },
        {
            "path": "HKLM:\\System\\CurrentControlSet\\Services",
            "description": "服务注册（仅检查可疑服务名）",
            "technique": "T1543.003",
        },
    ],
    "dll_injection": [
        {
            "path": "HKLM:\\Software\\Microsoft\\Windows NT\\CurrentVersion\\Windows",
            "description": "AppInit_DLLs DLL注入",
            "technique": "T1546.010",
            "check_key": "AppInit_DLLs",
        },
        {
            "path": "HKLM:\\Software\\Microsoft\\Windows NT\\CurrentVersion\\Image File Execution Options",
            "description": "IFEO 进程劫持",
            "technique": "T1546.012",
        },
    ],
    "credential_access": [
        {
            "path": "HKLM:\\System\\CurrentControlSet\\Control\\Lsa",
            "description": "LSA 凭据窃取配置",
            "technique": "T1003.004",
            "check_keys": ["Security Packages", "Authentication Packages"],
        },
        {
            "path": "HKLM:\\System\\CurrentControlSet\\Control\\SecurityProviders\\WDigest",
            "description": "WDigest 明文凭据",
            "technique": "T1003.001",
            "check_key": "UseLogonCredential",
        },
    ],
    "browser_hijack": [
        {
            "path": "HKLM:\\Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\Browser Helper Objects",
            "description": "浏览器劫持（BHO）",
            "technique": "T1189",
        },
    ],
    "uac_bypass": [
        {
            "path": "HKLM:\\Software\\Microsoft\\Windows\\CurrentVersion\\Policies\\System",
            "description": "UAC 配置（EnableLUA / ConsentPromptBehaviorAdmin）",
            "technique": "T1548.002",
            "check_keys": ["EnableLUA", "ConsentPromptBehaviorAdmin"],
        },
    ],
}

# 可疑值特征
SUSPICIOUS_VALUE_PATTERNS = [
    r"(?i)\\Temp\\",
    r"(?i)\\AppData\\",
    r"(?i)\\Users\\Public\\",
    r"(?i)\\ProgramData\\Temp\\",
    r"(?i)\.vbs$",
    r"(?i)\.ps1$",
    r"(?i)\.bat$",
    r"(?i)\.hta$",
    r"(?i)\.scr$",
]


def _check_registry_value(name: str, value: str) -> list:
    """检查注册表值是否可疑。"""
    import re
    flags = []
    for pattern in SUSPICIOUS_VALUE_PATTERNS:
        if re.search(pattern, str(value)):
            flags.append(f"可疑路径: {value[:100]}")
            break
    return flags


@tool("scan_registry", parse_docstring=True)
def scan_registry(
    scan_type: str = "all",
) -> str:
    """扫描注册表中的常见恶意软件驻留位置和安全配置。

    检查内容包括：启动项持久化、DLL注入配置、凭据窃取配置、
    UAC绕过配置、浏览器劫持等。

    Args:
        scan_type: 扫描类型，可选 "persistence" / "dll_injection" / "credential_access"
                   / "browser_hijack" / "uac_bypass" / "all"，默认 "all"。

    Returns:
        JSON 字符串，包含扫描结果和风险标记。
    """
    findings = []
    errors = []

    # 确定扫描范围
    if scan_type == "all":
        locations = {}
        for locs in SCAN_LOCATIONS.values():
            locations.update({l["path"]: l for l in locs})
    else:
        locs = SCAN_LOCATIONS.get(scan_type, [])
        locations = {l["path"]: l for l in locs}

    for path, info in locations.items():
        ps_cmd = (
            f"Get-ItemProperty -Path 'Registry::{path}' -ErrorAction SilentlyContinue | "
            "Select-Object -Property * -ExcludeProperty PSPath,PSParentPath,PSChildName,PSDrive,PSProvider,PSNotePropertyName | "
            "ConvertTo-Json -Depth 2"
        )

        r = run_powershell(ps_cmd, timeout=30)
        if not r["success"] or not r["stdout"]:
            continue

        props = safe_json_parse(r["stdout"])
        if isinstance(props, dict) and props.get("parse_error"):
            continue

        if isinstance(props, dict):
            for key, value in props.items():
                if key.startswith("PS"):
                    continue
                if value is None or value == "":
                    continue

                flags = _check_registry_value(key, str(value))
                if flags or info.get("check_key") == key or info.get("check_keys") and key in info.get("check_keys", []):
                    findings.append({
                        "path": path,
                        "key": key,
                        "value": str(value)[:200],
                        "description": info["description"],
                        "technique": info.get("technique", ""),
                        "suspicious": len(flags) > 0,
                        "flags": flags,
                    })

        # 特殊处理：IFEO 需要检查子键
        if "Image File Execution Options" in path:
            ps_subkeys = (
                f"Get-ChildItem -Path 'Registry::{path}' -ErrorAction SilentlyContinue | "
                "ForEach-Object { $_.PSChildName }"
            )
            r2 = run_powershell(ps_subkeys, timeout=30)
            if r2["success"] and r2["stdout"]:
                subkeys = [s.strip() for s in r2["stdout"].split("\n") if s.strip()]
                # 排除 Debugger 为空的正常项
                for sk in subkeys[:30]:  # 限制数量
                    if sk == "PsGetSid":
                        continue  # 忽略伪输出
                    ps_debugger = (
                        f"Get-ItemProperty -Path 'Registry::{path}\\{sk}' "
                        "-ErrorAction SilentlyContinue | Select-Object -ExpandProperty Debugger"
                    )
                    r3 = run_powershell(ps_debugger, timeout=10)
                    if r3["success"] and r3["stdout"]:
                        debugger = r3["stdout"].strip()
                        findings.append({
                            "path": f"{path}\\{sk}",
                            "key": "Debugger",
                            "value": debugger,
                            "description": f"IFEO 劫持: {sk}",
                            "technique": "T1546.012",
                            "suspicious": True,
                            "flags": [f"IFEO Debugger: {sk} -> {debugger}"],
                        })

    # 统计
    total = len(findings)
    suspicious = [f for f in findings if f.get("suspicious")]

    return format_result(
        success=True,
        data={
            "total_findings": total,
            "suspicious_count": len(suspicious),
            "scan_type": scan_type,
            "findings": findings,
        },
        error="; ".join(errors) if errors else None,
    )