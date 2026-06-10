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


def _parse_netstat(text: str, pid_name_map: dict = None) -> list:
    """解析 netstat -ano 输出为连接列表（非管理员回退路径）"""
    connections = []
    import re as _re

    if pid_name_map is None:
        pid_name_map = {}

    state_map = {
        "LISTENING": "listen", "ESTABLISHED": "established",
        "TIME_WAIT": "time_wait", "CLOSE_WAIT": "close_wait",
        "SYN_SENT": "syn_sent", "SYN_RECEIVED": "syn_received",
        "FIN_WAIT_1": "fin_wait1", "FIN_WAIT_2": "fin_wait2",
        "LAST_ACK": "last_ack", "CLOSING": "closing",
    }

    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("活动连接") or line.startswith("Active") or line.startswith("Proto"):
            continue

        parts = line.split()
        if len(parts) < 5:
            continue

        protocol = parts[0].lower()
        local = parts[1]
        remote = parts[2]
        state_str = parts[3] if len(parts) == 5 else ""
        pid_str = parts[-1]

        if not pid_str.isdigit():
            continue

        pid = int(pid_str)
        # 解析本地/远程地址:端口
        local_addr, local_port = "0.0.0.0", 0
        if ":" in local:
            # netstat 格式: [::1]:port 或 192.168.1.1:port
            if local.startswith("["):
                local_addr = local[1:local.index("]")]
                local_port = int(local.split("]:")[-1])
            else:
                addr_part, _, port_part = local.rpartition(":")
                local_addr = addr_part
                try:
                    local_port = int(port_part)
                except ValueError:
                    local_port = 0

        remote_addr, remote_port = "0.0.0.0", 0
        if ":" in remote and remote != "*:*":
            if remote.startswith("["):
                remote_addr = remote[1:remote.index("]")]
                remote_port = int(remote.split("]:")[-1])
            else:
                addr_part, _, port_part = remote.rpartition(":")
                remote_addr = addr_part
                try:
                    remote_port = int(port_part)
                except ValueError:
                    remote_port = 0

        state_mapped = state_map.get(state_str.upper(), state_str.lower())

        process_name = pid_name_map.get(pid, f"PID_{pid}")

        conn = {
            "protocol": protocol,
            "local_address": local_addr,
            "local_port": local_port,
            "remote_address": remote_addr,
            "remote_port": remote_port,
            "state": state_mapped,
            "pid": pid,
            "process_name": process_name,
            "created": "",
        }

        suspicion = _check_suspicious_connection(conn)
        conn.update(suspicion)
        connections.append(conn)

    return connections


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
    connections = []

    # 预构建 PID→进程名映射（一次性 Get-Process，避免逐连接查询）
    # 注意：tasklist 在本机可能卡死，使用 Get-Process 代替
    pid_name_map = {}
    try:
        ps_map_cmd = (
            "Get-Process | Select-Object Id,ProcessName | ConvertTo-Json -Depth 1"
        )
        map_r = run_powershell(ps_map_cmd, timeout=15)
        if map_r["success"] and map_r["stdout"]:
            procs = safe_json_parse(map_r["stdout"])
            if isinstance(procs, dict) and not procs.get("parse_error"):
                procs = [procs]
            if isinstance(procs, list):
                for p in procs:
                    pid = p.get("Id")
                    name = p.get("ProcessName", "")
                    if pid and name:
                        pid_name_map[int(pid)] = name
    except Exception:
        pass

    # ── 主路径：netstat -ano（无需管理员权限，始终可用） ──
    ns_cmd = "netstat -ano"
    ns_r = run_powershell(ns_cmd, timeout=30)
    if ns_r["success"] and ns_r["stdout"]:
        connections = _parse_netstat(ns_r["stdout"], pid_name_map)
        # 应用过滤器
        if filter_port is not None:
            connections = [c for c in connections if c.get("remote_port") == filter_port]
        if established_only:
            connections = [c for c in connections if c.get("state") == "established"]

    if not connections:
        return format_result(False, error="网络连接查询失败（netstat 无数据）")

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