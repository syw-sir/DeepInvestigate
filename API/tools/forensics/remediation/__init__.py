"""
处置工具包 (v4.1)

提供主机安全处置能力，所有工具 Risk Level 3，必须 HITL 审批。
每个操作前自动备份，支持回滚。

设计原则：
  - 最高安全级别：所有处置工具 Level 3，每次调用必须用户确认
  - 可回滚：文件隔离而非删除，注册表导出备份
  - 白名单保护：系统关键进程/文件/注册表项禁止操作
  - 操作审计：每次处置记录时间、操作、结果、回滚信息
"""

from .kill_process import kill_process
from .quarantine_file import quarantine_file
from .block_ip import block_ip
from .remove_startup import remove_startup
from .repair_registry import repair_registry
from .rollback import rollback_action

__all__ = [
    "kill_process",
    "quarantine_file",
    "block_ip",
    "remove_startup",
    "repair_registry",
    "rollback_action",
]
