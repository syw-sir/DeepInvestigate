"""
操作回滚工具 (v4.1)

回滚之前执行的处置操作。风险等级：Level 2。
仅能回滚本系统执行的操作（通过 action_id 验证）。
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import time
from datetime import datetime

from langchain_core.tools import tool

from .._utils import run_powershell, format_result

logger = logging.getLogger(__name__)

# 备份目录
BACKUP_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
    "workspace", "forensics_backups",
)

# 隔离目录
QUARANTINE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
    "workspace", "quarantine",
)


def _get_backup_dir():
    os.makedirs(BACKUP_DIR, exist_ok=True)
    return BACKUP_DIR


def _load_backup_record(action_id: str) -> dict:
    """加载备份记录。"""
    backup_file = os.path.join(_get_backup_dir(), f"{action_id}.json")
    if not os.path.exists(backup_file):
        return None
    try:
        with open(backup_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"加载备份记录失败: {e}")
        return None


def _rollback_kill_process(record: dict) -> dict:
    """回滚进程终止 - 无法自动恢复，提供提示信息。"""
    pid = record.get("pid", "unknown")
    process_name = record.get("process_name", "unknown")
    return {
        "success": True,
        "action_type": "kill_process",
        "note": f"进程终止无法自动回滚。进程 {process_name} (PID={pid}) 已被终止。",
        "suggestion": f"如需恢复，请重新启动相关程序或服务。",
    }


def _rollback_quarantine_file(record: dict) -> dict:
    """回滚文件隔离 - 从隔离区恢复文件。"""
    original_path = record.get("original_path", "")
    quarantine_path = record.get("quarantine_path", "")

    if not os.path.exists(quarantine_path):
        # 文件可能已被删除或从未隔离
        if os.path.exists(original_path):
            return {
                "success": True,
                "action_type": "quarantine_file",
                "note": f"隔离区文件不存在，但原始位置文件已存在。可能已被手动恢复。",
            }
        return {
            "success": False,
            "action_type": "quarantine_file",
            "error": f"隔离文件不存在: {quarantine_path}，且原始文件也不在: {original_path}",
        }

    try:
        # 移除占位文件
        if os.path.exists(original_path):
            os.remove(original_path)

        # 从隔离区恢复
        shutil.move(quarantine_path, original_path)
        return {
            "success": True,
            "action_type": "quarantine_file",
            "restored_to": original_path,
        }
    except Exception as e:
        # 尝试通过 PowerShell
        ps_cmd = (
            f"if (Test-Path '{original_path}') {{ Remove-Item '{original_path}' -Force }}; "
            f"Move-Item -Path '{quarantine_path}' -Destination '{original_path}' -Force"
        )
        r = run_powershell(ps_cmd, timeout=15)
        return {
            "success": r["success"],
            "action_type": "quarantine_file",
            "restored_to": original_path if r["success"] else None,
            "error": None if r["success"] else (r["error"] or r["stderr"]),
        }


def _rollback_block_ip(record: dict) -> dict:
    """回滚 IP 封禁 - 删除防火墙规则。"""
    rollback_cmd = record.get("rollback_cmd", "")
    results = []

    # 从记录中获取规则列表
    rules = record.get("rules", [])
    if not rules:
        # 尝试使用 rollback_cmd
        if rollback_cmd:
            r = run_powershell(rollback_cmd, timeout=20)
            return {
                "success": r["success"],
                "action_type": "block_ip",
                "removed_rules": [rollback_cmd],
                "error": None if r["success"] else r.get("error"),
            }
        return {"success": False, "action_type": "block_ip", "error": "无规则信息可回滚"}

    all_success = True
    for rule in rules:
        rule_name = rule.get("rule_name", "")
        if rule_name:
            cmd = f'netsh advfirewall firewall delete rule name="{rule_name}"'
            r = run_powershell(cmd, timeout=10)
            results.append({
                "rule_name": rule_name,
                "success": r["success"],
                "output": r["stdout"],
            })
            if not r["success"]:
                all_success = False

    return {
        "success": all_success,
        "action_type": "block_ip",
        "removed_rules": [r["rule_name"] for r in results],
        "details": results,
    }


def _rollback_remove_startup(record: dict) -> dict:
    """回滚启动项删除 - 从备份恢复。"""
    source = record.get("source", "")
    identifier = record.get("identifier", "")
    backup_file = record.get("backup", "")
    action_id = record.get("action_id", "")
    # backup file is stored at BACKUP_DIR/action_id.reg or .xml or _svc.txt
    reg_backup = os.path.join(_get_backup_dir(), f"{action_id}.reg")
    xml_backup = os.path.join(_get_backup_dir(), f"{action_id}.xml")
    svc_backup = os.path.join(_get_backup_dir(), f"{action_id}_svc.txt")

    if source == "registry":
        if os.path.exists(reg_backup):
            # 导入 .reg 备份文件
            cmd = f'reg import "{reg_backup}"'
            r = run_powershell(cmd, timeout=10)
            return {
                "success": r["success"],
                "action_type": "remove_startup",
                "restored_identifier": identifier,
                "source": source,
                "error": None if r["success"] else (r["error"] or r["stderr"]),
            }
        return {"success": False, "action_type": "remove_startup", "error": f"备份文件不存在: {reg_backup}"}

    elif source == "task":
        if os.path.exists(xml_backup):
            # 从 XML 备份恢复计划任务
            cmd = f'schtasks /create /tn "{identifier}" /xml "{xml_backup}" /f'
            r = run_powershell(cmd, timeout=15)
            return {
                "success": r["success"],
                "action_type": "remove_startup",
                "restored_identifier": identifier,
                "source": source,
                "error": None if r["success"] else (r["error"] or r["stderr"]),
            }
        return {"success": False, "action_type": "remove_startup", "error": f"备份文件不存在: {xml_backup}"}

    else:  # service
        if os.path.exists(svc_backup):
            # 重新启用服务
            enable_cmd = f'sc config "{identifier}" start= demand'
            start_cmd = f'sc start "{identifier}"'
            r1 = run_powershell(enable_cmd, timeout=10)
            r2 = run_powershell(start_cmd, timeout=15)
            success = r1["success"]
            return {
                "success": success,
                "action_type": "remove_startup",
                "restored_identifier": identifier,
                "source": source,
                "note": f"服务 {identifier} 已尝试恢复为手动启动模式",
                "error": None if success else (r1.get("error") or r1.get("stderr")),
            }
        return {"success": False, "action_type": "remove_startup", "error": f"备份文件不存在: {svc_backup}"}


def _rollback_repair_registry(record: dict) -> dict:
    """回滚注册表修复 - 从 .reg 备份恢复。"""
    path = record.get("path", "")
    key = record.get("key", "")
    backup_file = record.get("backup_file", "")

    if backup_file and os.path.exists(backup_file):
        # 导入 .reg 备份文件
        cmd = f'reg import "{backup_file}"'
        r = run_powershell(cmd, timeout=10)
        return {
            "success": r["success"],
            "action_type": "repair_registry",
            "restored_path": f"{path}\\{key}",
            "error": None if r["success"] else (r["error"] or r["stderr"]),
        }

    # 尝试标准备份路径
    backup_record = os.path.join(_get_backup_dir(), f"{record.get('action_id', '')}.reg")
    if os.path.exists(backup_record):
        cmd = f'reg import "{backup_record}"'
        r = run_powershell(cmd, timeout=10)
        return {
            "success": r["success"],
            "action_type": "repair_registry",
            "restored_path": f"{path}\\{key}",
            "error": None if r["success"] else (r["error"] or r["stderr"]),
        }

    return {"success": False, "action_type": "repair_registry", "error": "备份文件不存在，无法回滚"}


# 回滚处理函数映射
_ROLLBACK_HANDLERS = {
    "kill_process": _rollback_kill_process,
    "quarantine_file": _rollback_quarantine_file,
    "block_ip": _rollback_block_ip,
    "remove_startup": _rollback_remove_startup,
    "repair_registry": _rollback_repair_registry,
}


@tool("rollback_action", parse_docstring=True)
def rollback_action(
    action_id: str,
) -> str:
    """回滚之前执行的处置操作。

    根据操作 ID 从备份中恢复文件/注册表/防火墙规则/服务配置。
    仅能回滚本系统执行过的操作（通过 action_id 验证备份记录是否存在）。

    Args:
        action_id: 之前处置操作返回的操作 ID（如 kill_2844_1718123456）。

    Returns:
        JSON 字符串，包含回滚结果和恢复的项目信息。
    """
    # 加载备份记录
    record = _load_backup_record(action_id)
    if record is None:
        return format_result(
            False,
            error=f"未找到操作记录: {action_id}。该操作可能不存在或备份已过期。",
        )

    action_type = record.get("action", "")
    if not action_type:
        return format_result(
            False,
            error=f"操作记录中缺少 action 类型: {action_id}",
        )

    # 查找对应的回滚处理函数
    handler = _ROLLBACK_HANDLERS.get(action_type)
    if handler is None:
        return format_result(
            False,
            error=f"不支持回滚的操作类型: {action_type}",
        )

    # 执行回滚
    try:
        result = handler(record)
        result["action_id"] = action_id
        result["timestamp"] = datetime.now().isoformat()

        # 更新备份记录，标记为已回滚
        record["rolled_back"] = True
        record["rollback_timestamp"] = result["timestamp"]
        record["rollback_result"] = result

        backup_file = os.path.join(_get_backup_dir(), f"{action_id}.json")
        try:
            with open(backup_file, "w", encoding="utf-8") as f:
                json.dump(record, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

        return format_result(
            success=result.get("success", False),
            data=result,
            error=result.get("error"),
        )
    except Exception as e:
        return format_result(
            False,
            error=f"回滚执行失败: {type(e).__name__}: {e}",
        )
