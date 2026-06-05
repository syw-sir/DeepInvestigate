"""
主机取证工具包 (v4.0)

提供自主主机安全调查能力，所有工具默认只读，不修改主机状态。
"""

from .system_info import collect_system_info
from .process_scanner import scan_processes
from .network_monitor import check_network
from .login_auditor import audit_logins
from .startup_checker import check_startup
from .registry_scanner import scan_registry
from .file_integrity import check_file_integrity
from .defender_checker import check_defender_logs

__all__ = [
    "collect_system_info",
    "scan_processes",
    "check_network",
    "audit_logins",
    "check_startup",
    "scan_registry",
    "check_file_integrity",
    "check_defender_logs",
]