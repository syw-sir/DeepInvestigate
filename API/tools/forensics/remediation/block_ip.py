"""
IP 封禁工具 (v4.1)

通过 Windows 防火墙封禁可疑 IP。风险等级：Level 3（必须 HITL 审批）。
"""

from __future__ import annotations

import ipaddress
import json
import logging
import os
import time
from datetime import datetime

from langchain_core.tools import tool

from .._utils import run_powershell, format_result

logger = logging.getLogger(__name__)

# 内网 IP 保护（默认不封禁）
PROTECTED_NETWORKS = [
    "127.0.0.0/8",
    "10.0.0.0/8",
    "172.16.0.0/12",
    "192.168.0.0/16",
    "0.0.0.0/8",
    "224.0.0.0/4",    # 多播
    "240.0.0.0/4",    # 保留
]

# 备份目录
BACKUP_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
    "workspace", "forensics_backups",
)


def _is_private_ip(ip_str: str) -> bool:
    """检查 IP 是否为内网地址。"""
    try:
        ip = ipaddress.ip_address(ip_str)
        return ip.is_private or ip.is_loopback or ip.is_multicast or ip.is_reserved
    except ValueError:
        return False


def _get_backup_dir():
    os.makedirs(BACKUP_DIR, exist_ok=True)
    return BACKUP_DIR


@tool("block_ip", parse_docstring=True)
def block_ip(
    ip: str,
    direction: str = "outbound",
) -> str:
    """通过 Windows 防火墙封禁指定 IP。

    使用 netsh advfirewall 添加防火墙规则，默认封禁出站连接。
    内网 IP（192.168./10./172.16./127.）默认不封禁，除非显式确认。

    Args:
        ip: 要封禁的 IPv4 地址（如 45.33.32.156）。
        direction: 封禁方向，"outbound"（出站）、"inbound"（入站）或 "both"（双向）。

    Returns:
        JSON 字符串，包含操作结果和回滚信息。
    """
    # 验证 IP 格式
    try:
        ipaddress.ip_address(ip)
    except ValueError:
        return format_result(False, error=f"无效的 IP 地址: {ip}")

    # 检查内网 IP 保护
    if _is_private_ip(ip):
        return format_result(
            False,
            error=f"禁止封禁内网/保留 IP: {ip}（受保护网络范围）",
        )

    # 验证 direction
    valid_directions = ["outbound", "inbound", "both"]
    if direction not in valid_directions:
        return format_result(
            False,
            error=f"无效的 direction 参数: {direction}，可选值: {', '.join(valid_directions)}",
        )

    action_id = f"blockip_{ip.replace('.', '_')}_{int(time.time())}"
    timestamp = datetime.now().isoformat()

    dirs_to_block = []
    if direction in ("outbound", "both"):
        dirs_to_block.append("out")
    if direction in ("inbound", "both"):
        dirs_to_block.append("in")

    results = []
    all_success = True

    for d in dirs_to_block:
        rule_name = f"DeepInvestigate_Block_{ip}_{d}"
        # 先删除已存在的同名规则
        run_powershell(
            f"netsh advfirewall firewall delete rule name=\"{rule_name}\"",
            timeout=10,
        )

        # 添加封禁规则
        cmd = (
            f"netsh advfirewall firewall add rule "
            f"name=\"{rule_name}\" dir={d} remoteip={ip} action=block"
        )
        r = run_powershell(cmd, timeout=15)

        success = r["success"]
        all_success = all_success and success

        results.append({
            "direction": d,
            "rule_name": rule_name,
            "success": success,
            "output": r["stdout"] if success else (r["error"] or r["stderr"]),
        })

    # 保存备份记录
    backup_info = {
        "action": "block_ip",
        "action_id": action_id,
        "ip": ip,
        "direction": direction,
        "rules": results,
        "timestamp": timestamp,
        "rollback_cmd": " & ".join([
            f"netsh advfirewall firewall delete rule name=\"{r['rule_name']}\""
            for r in results
        ]),
    }

    backup_file = os.path.join(_get_backup_dir(), f"{action_id}.json")
    try:
        with open(backup_file, "w", encoding="utf-8") as f:
            json.dump(backup_info, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning(f"备份记录保存失败: {e}")

    return format_result(
        success=all_success,
        data={
            "action": "block_ip",
            "action_id": action_id,
            "ip": ip,
            "direction": direction,
            "rules": results,
            "rollback_command": backup_info["rollback_cmd"],
        },
        error=None if all_success else "部分规则添加失败",
    )
