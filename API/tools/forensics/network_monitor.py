"""
网络连接检查工具 (v4.0)

检查当前网络连接状态，识别可疑外联。
风险等级：Level 1（读取网络状态，不修改）
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from langchain_core.tools import tool

from ._utils import run_powershell, safe_json_parse, format_result

logger = logging.getLogger(__name__)

# 常见非标准端口（可能用于 C2 / 后门）
SUSPICIOUS_PORTS = {4444, 5555, 6666, 6667, 7777, 8000, 8080, 8443, 8888, 9001, 9999, 1337, 31337}

# 常见合法端口（Web、邮件等）
LEGIT_PORTS = {80, 443, 22, 25, 53, 110, 143, 993, 995, 587, 465, 3389}

# 系统进程名（不应主动发起外部连接的进程）
SYSTEM_ONLY_PROCESSES = {"svchost.exe", "lsass.exe", "csrss.exe", "smss.exe", "winlogon.exe"}


def _check_suspicious_connection(conn: dict) -> dict:
    """检查单个连接是否可疑。"""
    flags = []
    remote_port = conn.get("remote_port", 0)
    remote_ip = conn.get("remote_address", "")
    process_name = (conn.get("process_name") or "").lower()
    state = (conn.get("state") or "").lower()

    # 1. 非标准端口且非 Web
    if remote_port in SUSPICIOUS_PORTS:
        flags.append(f"可疑端口: {remote_port}")

    # 2. 系统进程连接外部 IP
    if process_name in SYSTEM_ONLY_PROCESSES and not remote_ip.startswith(("127.", "0.", "192.168.", "10.", "172.")):
        flags.append(f"系统进程外联: {process_name} -> {remote_ip}:{remote_port}")

    # 3. 非标准端口上的 ESTABLISHED 连接（可能是 C2）
    if state == "established" and remote_port not in LEGIT_PORTS and remote_port > 1024:
        if not remote_ip.startswith(("127.", "192.168.", "10.", "172.")):
            flags.append(f"非标准端口外联: :{remote_port} -> {remote_ip}")

    # 4. 监听端口异常（非管理员进程监听低端口）
    if state == "listen" and remote_port < 1024 and remote_port not in LEGIT_PORTS:
        flags.append(f"低端口监听: {remote_port}")

    return {
        "suspicious": len(flags) > 0,
        "flags": flags,
    }


@tool("check_network", parse_docstring=True)
def check_network(
    filter_port: Optional[int] = None,
    established_only: bool = False,
) -> str:
    """检查当前主机的网络连接状态，识别可疑外联和监听。

    Args:
        filter_port: 可选，按远程端口过滤。
        established_only: 是否仅返回已建立（ESTABLISHED）的连接，默认 False 返回全部。

    Returns:
        JSON 字符串，包含网络连接列表和可疑分析。
    """
    # 使用 Get-NetTCPConnection 获取 TCP 连接
    ps_tcp = (
        "Get-NetTCPConnection | "
        "Select-Object LocalAddress,LocalPort,RemoteAddress,RemotePort,State,"
        "OwningProcess,@{Name='CreationTime';Expression={(Get-Process -Id $_.OwningProcess -ErrorAction SilentlyContinue).StartTime}} | "
        "ConvertTo-Json -Depth 2"
    )

    r = run_powershell(ps_tcp, timeout=60)
    if not r["success"]:
        return format_result(False, error=r["error"] or r["stderr"])

    raw_connections = safe_json_parse(r["stdout"])
    if isinstance(raw_connections, dict) and not raw_connections.get("parse_error"):
        raw_connections = [raw_connections]
    if not isinstance(raw_connections, list):
        return format_result(False, error="网络连接数据解析失败")

    connections = []
    for conn in raw_connections:
        remote_port = conn.get("RemotePort", 0)
        state = conn.get("State", 0)

        if filter_port is not None and remote_port != filter_port:
            continue

        if established_only and state != 5:  # 5 = Established
            continue

        # 获取进程名
        pid = conn.get("OwningProcess")
        process_name = ""
        if pid:
            ps_pname = (
                f"Get-Process -Id {pid} -ErrorAction SilentlyContinue | "
                "Select-Object -ExpandProperty ProcessName"
            )
            pr = run_powershell(ps_pname, timeout=10)
            if pr["success"] and pr["stdout"]:
                process_name = pr["stdout"].strip()

        # 状态映射
        state_map = {
            1: "closed", 2: "listen", 3: "syn_sent", 4: "syn_received",
            5: "established", 6: "fin_wait1", 7: "fin_wait2",
            8: "close_wait", 9: "closing", 10: "last_ack",
            11: "time_wait", 12: "delete_tcb",
        }
        state_str = state_map.get(state, f"unknown({state})")

        enhanced = {
            "protocol": "tcp",
            "local_address": conn.get("LocalAddress", ""),
            "local_port": conn.get("LocalPort", 0),
            "remote_address": conn.get("RemoteAddress", ""),
            "remote_port": remote_port,
            "state": state_str,
            "pid": pid,
            "process_name": process_name,
            "created": str(conn.get("CreationTime") or ""),
        }

        # 可疑分析
        suspicion = _check_suspicious_connection(enhanced)
        enhanced.update(suspicion)

        connections.append(enhanced)

    # 统计
    total = len(connections)
    suspicious_count = sum(1 for c in connections if c.get("suspicious"))
    unique_remote_ips = len(set(c["remote_address"] for c in connections if c["remote_address"] not in ("0.0.0.0", "::", "")))
    listening_ports = [c for c in connections if c["state"] == "listen"]

    return format_result(
        success=True,
        data={
            "total_connections": total,
            "suspicious_count": suspicious_count,
            "unique_remote_ips": unique_remote_ips,
            "listening_ports": len(listening_ports),
            "filter_port": filter_port,
            "established_only": established_only,
            "connections": connections,
        },
    )