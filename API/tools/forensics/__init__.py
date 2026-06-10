"""
主机取证工具包 (v4.0 + v4.1)

提供自主主机安全调查与处置能力。
- v4.0: 8 个只读取证工具
- v4.1: 6 个处置工具（需 HITL 审批）
"""

from .system_info import collect_system_info
from .process_scanner import scan_processes
from .network_monitor import check_network
from .login_auditor import audit_logins
from .startup_checker import check_startup
from .registry_scanner import scan_registry
from .file_integrity import check_file_integrity
from .defender_checker import check_defender_logs

# v4.1 处置工具
from .remediation.kill_process import kill_process
from .remediation.quarantine_file import quarantine_file
from .remediation.block_ip import block_ip
from .remediation.remove_startup import remove_startup
from .remediation.repair_registry import repair_registry
from .remediation.rollback import rollback_action

__all__ = [
    # v4.0 取证
    "collect_system_info",
    "scan_processes",
    "check_network",
    "audit_logins",
    "check_startup",
    "scan_registry",
    "check_file_integrity",
    "check_defender_logs",
    # v4.1 处置
    "kill_process",
    "quarantine_file",
    "block_ip",
    "remove_startup",
    "repair_registry",
    "rollback_action",
]