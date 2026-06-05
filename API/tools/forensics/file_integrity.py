"""
文件完整性检查工具 (v4.0)

检查关键系统文件是否被篡改，扫描可疑文件。
风险等级：Level 1（文件扫描，只读，不修改）
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from langchain_core.tools import tool

from ._utils import run_powershell, safe_json_parse, format_result

logger = logging.getLogger(__name__)

# 默认检查的关键目录
KEY_DIRECTORIES = [
    "C:\\Windows\\System32",
    "C:\\Windows\\Temp",
    "$env:TEMP",
    "$env:LOCALAPPDATA + '\\Temp'",
    "C:\\Users\\Public",
    "C:\\ProgramData",
]

# 可疑文件扩展名
SUSPICIOUS_EXTENSIONS = {".exe", ".dll", ".bat", ".cmd", ".ps1", ".vbs", ".hta", ".scr", ".pif", ".js", ".jse", ".wsf", ".wsh"}

# 隐藏属性和 ADS
HIDDEN_ATTRIBUTES = {"Hidden", "System", "ReadOnly", "Archive"}


@tool("check_file_integrity", parse_docstring=True)
def check_file_integrity(
    path: Optional[str] = None,
    quick: bool = False,
) -> str:
    """检查系统文件完整性，发现可疑文件。

    检查内容包括：关键目录中最近新增/修改的可执行文件、临时目录中的可执行文件、
    隐藏文件和 Alternate Data Streams (ADS)、关键 DLL 文件哈希。

    Args:
        path: 可选，指定要扫描的目录路径。不指定则扫描默认关键目录。
        quick: 快速模式，仅检查临时目录和最近7天修改文件，默认 False 完整扫描。

    Returns:
        JSON 字符串，包含扫描结果和可疑文件列表。
    """
    findings = []
    errors = []

    # 确定扫描目录
    if path:
        dirs_to_scan = [path]
    elif quick:
        dirs_to_scan = [
            "C:\\Windows\\Temp",
            "$env:TEMP",
            "$env:LOCALAPPDATA + '\\Temp'",
        ]
    else:
        dirs_to_scan = [
            "C:\\Windows\\System32",
            "C:\\Windows\\Temp",
            "$env:TEMP",
            "$env:LOCALAPPDATA + '\\Temp'",
        ]

    seven_days_ago = "(Get-Date).AddDays(-7)"

    for scan_dir in dirs_to_scan:
        # ---- 1. 最近修改的可执行文件 ----
        ps_recent = (
            f"Get-ChildItem -Path {scan_dir} -Recurse -Depth 2 -ErrorAction SilentlyContinue | "
            f"Where-Object {{$_.LastWriteTime -gt {seven_days_ago} -and "
            f"$_.Extension -match '\\.(exe|dll|bat|cmd|ps1|vbs|hta|scr)$'}} | "
            "Select-Object Name,FullName,LastWriteTime,Length,"
            "@{Name='Owner';Expression={(Get-Acl $_.FullName -ErrorAction SilentlyContinue).Owner}} | "
            "Sort-Object LastWriteTime -Descending | Select-Object -First 50 | ConvertTo-Json"
        )

        r = run_powershell(ps_recent, timeout=120)
        if r["success"] and r["stdout"]:
            files = safe_json_parse(r["stdout"])
            if isinstance(files, dict) and not files.get("parse_error"):
                files = [files]
            if isinstance(files, list):
                for f in files:
                    fullpath = f.get("FullName", "")
                    findings.append({
                        "type": "recently_modified",
                        "path": fullpath,
                        "name": f.get("Name", ""),
                        "modified": str(f.get("LastWriteTime", "")),
                        "size_bytes": f.get("Length", 0),
                        "owner": f.get("Owner", ""),
                        "directory": scan_dir,
                    })

        # ---- 2. 临时目录中的可执行文件（高度可疑） ----
        if "Temp" in scan_dir or "temp" in scan_dir.lower():
            ps_temp_exe = (
                f"Get-ChildItem -Path {scan_dir} -Recurse -Depth 1 -ErrorAction SilentlyContinue | "
                "Where-Object {$_.Extension -match '\\.(exe|dll|bat|ps1|vbs|scr)$'} | "
                "Select-Object Name,FullName,LastWriteTime,Length | ConvertTo-Json"
            )
            r2 = run_powershell(ps_temp_exe, timeout=60)
            if r2["success"] and r2["stdout"]:
                temp_files = safe_json_parse(r2["stdout"])
                if isinstance(temp_files, dict) and not temp_files.get("parse_error"):
                    temp_files = [temp_files]
                if isinstance(temp_files, list):
                    for f in temp_files:
                        fullpath = f.get("FullName", "")
                        findings.append({
                            "type": "executable_in_temp",
                            "path": fullpath,
                            "name": f.get("Name", ""),
                            "modified": str(f.get("LastWriteTime", "")),
                            "size_bytes": f.get("Length", 0),
                            "risk": "high",
                            "reason": "临时目录中的可执行文件高度可疑",
                        })

        # ---- 3. Alternate Data Streams (ADS) ----
        if not quick:
            ps_ads = (
                f"Get-ChildItem -Path {scan_dir} -Recurse -Depth 1 -ErrorAction SilentlyContinue | "
                "ForEach-Object { $path = $_.FullName; Get-Item -Path $path -Stream * -ErrorAction SilentlyContinue | "
                "Where-Object {$_.Stream -ne ':$DATA'} | Select-Object FileName,Stream,Length } | "
                "Select-Object -First 30 | ConvertTo-Json"
            )
            r3 = run_powershell(ps_ads, timeout=60)
            if r3["success"] and r3["stdout"]:
                ads_files = safe_json_parse(r3["stdout"])
                if isinstance(ads_files, dict) and not ads_files.get("parse_error"):
                    ads_files = [ads_files]
                if isinstance(ads_files, list):
                    for a in ads_files:
                        findings.append({
                            "type": "alternate_data_stream",
                            "path": a.get("FileName", ""),
                            "stream": a.get("Stream", ""),
                            "size_bytes": a.get("Length", 0),
                            "risk": "medium",
                            "reason": "ADS 可能隐藏恶意载荷",
                        })

    # ---- 4. 关键 DLL 哈希计算 ----
    if not quick and not path:
        critical_dlls = [
            "C:\\Windows\\System32\\ntdll.dll",
            "C:\\Windows\\System32\\kernel32.dll",
            "C:\\Windows\\System32\\ws2_32.dll",
            "C:\\Windows\\System32\\wininet.dll",
        ]
        hash_results = []
        for dll in critical_dlls:
            ps_hash = f"Get-FileHash -Path '{dll}' -Algorithm SHA256 -ErrorAction SilentlyContinue | Select-Object Hash | ConvertTo-Json"
            r4 = run_powershell(ps_hash, timeout=30)
            if r4["success"] and r4["stdout"]:
                h = safe_json_parse(r4["stdout"])
                hash_results.append({
                    "file": dll,
                    "sha256": h.get("Hash", "") if isinstance(h, dict) else "",
                })

        findings.append({
            "type": "file_hashes",
            "files": hash_results,
        })

    # 去重
    seen = set()
    unique_findings = []
    for f in findings:
        key = f.get("path", "") + f.get("type", "")
        if key not in seen:
            seen.add(key)
            unique_findings.append(f)

    # 统计
    high_risk = [f for f in unique_findings if f.get("risk") == "high"]
    medium_risk = [f for f in unique_findings if f.get("risk") == "medium"]

    return format_result(
        success=True,
        data={
            "total_findings": len(unique_findings),
            "high_risk_count": len(high_risk),
            "medium_risk_count": len(medium_risk),
            "quick_mode": quick,
            "scanned_dirs": dirs_to_scan,
            "findings": unique_findings[:100],
        },
        error="; ".join(errors) if errors else None,
    )