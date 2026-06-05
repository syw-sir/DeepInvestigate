"""
登录审计工具 (v4.0)

审计 Windows 安全事件日志中的登录事件，识别暴力破解、异常登录等。
风险等级：Level 2（读取安全日志，可能触发审计，需要管理员权限）
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from langchain_core.tools import tool

from ._utils import run_powershell, safe_json_parse, format_result

logger = logging.getLogger(__name__)

DEFAULT_HOURS_BACK = 24

# 关键事件 ID
SECURITY_EVENTS = {
    4624: "登录成功",
    4625: "登录失败",
    4648: "显式凭据登录",
    4672: "特权分配",
    4776: "NTLM认证",
    4720: "用户账户创建",
    4722: "用户账户启用",
    4728: "组成员添加",
    4732: "安全组添加成员",
}

# 登录类型映射
LOGON_TYPES = {
    2: "交互式登录(本地)",
    3: "网络登录",
    4: "批处理登录",
    5: "服务登录",
    7: "解锁",
    8: "网络明文登录",
    9: "新凭据登录",
    10: "远程交互式(RDP)",
    11: "缓存交互式登录",
}

# 可疑登录特征阈值
BRUTE_FORCE_THRESHOLD = 10  # 短时间内失败登录次数阈值
OFF_HOURS_START = 20  # 非工作时间起始（晚8点）
OFF_HOURS_END = 6     # 非工作时间结束（早6点）


def _check_suspicious_login(events: list) -> dict:
    """分析登录事件，识别可疑模式。"""
    flags = []
    details = {}

    # 统计失败登录（按用户名）
    failed_by_user = {}
    for e in events:
        if e.get("event_id") == 4625:
            user = e.get("target_user", "unknown")
            failed_by_user[user] = failed_by_user.get(user, 0) + 1

    # 暴力破解检测
    for user, count in failed_by_user.items():
        if count >= BRUTE_FORCE_THRESHOLD:
            flags.append(f"暴力破解: {user} ({count}次失败登录)")
            details["brute_force"] = details.get("brute_force", [])
            details["brute_force"].append({"user": user, "failures": count})

    # 非工作时间登录
    off_hours_logins = []
    for e in events:
        if e.get("event_id") == 4624:
            time_str = e.get("time", "")
            try:
                from datetime import datetime
                ts = datetime.fromisoformat(time_str)
                hour = ts.hour
                if hour >= OFF_HOURS_START or hour < OFF_HOURS_END:
                    off_hours_logins.append(e)
            except Exception:
                pass

    if off_hours_logins:
        flags.append(f"非工作时间登录: {len(off_hours_logins)}次")
        details["off_hours_logins"] = len(off_hours_logins)

    # RDP 登录来源
    rdp_logins = [e for e in events if e.get("event_id") == 4624 and e.get("logon_type") == 10]
    if rdp_logins:
        rdp_sources = set(e.get("source_ip", "") for e in rdp_logins if e.get("source_ip"))
        flags.append(f"RDP登录来源: {rdp_sources}")
        details["rdp_sources"] = list(rdp_sources)

    # 新增账户
    new_accounts = [e for e in events if e.get("event_id") == 4720]
    if new_accounts:
        flags.append(f"新创建用户账户: {len(new_accounts)}个")
        details["new_accounts"] = len(new_accounts)

    return {
        "suspicious": len(flags) > 0,
        "flags": flags,
        "details": details,
    }


def _parse_event_xml(xml_str: str) -> dict:
    """从 Windows Event XML 中提取关键字段。"""
    import re

    result = {}

    # 事件 ID
    m = re.search(r"<EventID[^>]*>(\d+)</EventID>", xml_str)
    if m:
        result["event_id"] = int(m.group(1))

    # 时间
    m = re.search(r"<TimeCreated SystemTime='([^']+)'", xml_str)
    if m:
        result["time"] = m.group(1)

    # 从 Data 字段提取信息
    data_fields = re.findall(r"<Data Name='([^']+)'>(.*?)</Data>", xml_str)
    for name, value in data_fields:
        if name == "TargetUserName":
            result["target_user"] = value
        elif name == "SubjectUserName":
            result["subject_user"] = value
        elif name == "IpAddress":
            result["source_ip"] = value
        elif name == "LogonType":
            try:
                lt = int(value)
                result["logon_type"] = lt
                result["logon_type_desc"] = LOGON_TYPES.get(lt, f"未知({lt})")
            except ValueError:
                result["logon_type"] = value
        elif name == "WorkstationName":
            result["workstation"] = value

    return result


@tool("audit_logins", parse_docstring=True)
def audit_logins(
    hours_back: int = DEFAULT_HOURS_BACK,
    event_ids: Optional[str] = None,
) -> str:
    """审计 Windows 安全事件日志中的登录相关事件。

    查询安全日志中的登录成功/失败、特权分配、账户变更等事件，
    并自动分析暴力破解、非工作时间登录、RDP异常登录等可疑行为。

    注意：此工具需要管理员权限才能读取安全事件日志。

    Args:
        hours_back: 回溯小时数，默认 24。
        event_ids: 可选，逗号分隔的事件ID，如 "4624,4625"。默认查询所有关键事件。

    Returns:
        JSON 字符串，包含登录事件列表和可疑分析结果。
    """
    # 构建事件 ID 过滤
    if event_ids:
        ids = [int(x.strip()) for x in event_ids.split(",") if x.strip().isdigit()]
    else:
        ids = list(SECURITY_EVENTS.keys())

    id_filter = " or ".join([f"EventID={eid}" for eid in ids])
    cutoff = f"(Get-Date).AddHours(-{hours_back})"

    # 使用 Get-WinEvent 查询（比 wevtutil 更快更可靠）
    ps_cmd = (
        f"Get-WinEvent -FilterHashtable @{{LogName='Security'; {id_filter}; StartTime={cutoff}}} "
        "-MaxEvents 200 -ErrorAction SilentlyContinue | "
        "ForEach-Object { $_.ToXml() }"
    )

    r = run_powershell(ps_cmd, timeout=90)
    if not r["success"]:
        # 权限不足时返回友好提示
        if "Access is denied" in r.get("stderr", "") or "拒绝访问" in r.get("stderr", ""):
            return format_result(
                False,
                error="权限不足：读取安全事件日志需要管理员权限，请以管理员身份运行程序",
            )
        return format_result(False, error=r["error"] or r["stderr"])

    # 解析 XML 事件
    import re
    xml_events = re.findall(r"<Event[^>]*>.*?</Event>", r["stdout"], re.DOTALL)
    if not xml_events:
        # 尝试另一种解析方式
        xml_events = r["stdout"].split("<Event ")[1:]
        xml_events = ["<Event " + e for e in xml_events]

    events = []
    for xml_str in xml_events:
        parsed = _parse_event_xml(xml_str)
        if parsed.get("event_id"):
            parsed["event_desc"] = SECURITY_EVENTS.get(parsed["event_id"], "未知事件")
            events.append(parsed)

    if not events:
        return format_result(
            success=True,
            data={
                "total_events": 0,
                "message": "未找到符合条件的登录事件",
                "hours_back": hours_back,
            },
        )

    # 统计分析
    suspicion = _check_suspicious_login(events)

    event_id_counts = {}
    for e in events:
        eid = e.get("event_id", 0)
        event_id_counts[eid] = event_id_counts.get(eid, 0) + 1

    return format_result(
        success=True,
        data={
            "total_events": len(events),
            "hours_back": hours_back,
            "event_id_counts": event_id_counts,
            "suspicious": suspicion["suspicious"],
            "suspicion_flags": suspicion["flags"],
            "suspicion_details": suspicion["details"],
            "events": events[:50],  # 只返回前 50 条，避免过大
        },
    )