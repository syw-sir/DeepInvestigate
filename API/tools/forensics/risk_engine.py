"""
风险评分引擎 (v4.0)

根据取证工具采集的结果，计算主机风险评分 (0-100)。

评分逻辑：
- 基础分：每种威胁指标按配置权重累加
- 关联加权：同一实体（如同一个PID）同时触发多项指标，额外加权
- 置信度调整：低置信度指标权重打折
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# 默认评分配置
DEFAULT_RISK_CONFIG = {
    "suspicious_process": 15,
    "suspicious_network": 15,
    "failed_logins_spike": 20,
    "unsigned_startup": 20,
    "registry_anomaly": 15,
    "file_anomaly": 15,
    "defender_alert": 25,
    "correlation_multiplier": 1.5,
    "threat_threshold": 40,
}

# 威胁等级定义
RISK_LEVELS = [
    (0, "正常"),
    (20, "低风险"),
    (40, "中风险"),
    (60, "高风险"),
    (80, "严重"),
]


def _load_config() -> dict:
    """从 config.yaml 加载风险评分配置。"""
    try:
        from config_deepseek import config as raw_config
        fc = raw_config.get("forensics", {}).get("risk_scoring", {})
        if fc:
            return {**DEFAULT_RISK_CONFIG, **fc}
    except Exception:
        pass
    return DEFAULT_RISK_CONFIG


def _get_risk_level(score: float) -> str:
    """将数值评分转为风险等级文字。"""
    for threshold, label in reversed(RISK_LEVELS):
        if score >= threshold:
            return label
    return "正常"


def _extract_indicators_from_processes(processes: list) -> List[Dict]:
    """从进程扫描结果提取威胁指标。"""
    indicators = []
    for proc in processes:
        if not proc.get("suspicious"):
            continue
        indicators.append({
            "type": "suspicious_process",
            "value": f"PID {proc.get('pid')} {proc.get('name')}",
            "confidence": "medium" if proc.get("suspicion_level", 0) >= 2 else "low",
            "entity_id": str(proc.get("pid")),  # 用于关联
            "flags": proc.get("flags", []),
        })
    return indicators


def _extract_indicators_from_network(connections: list) -> List[Dict]:
    """从网络连接扫描结果提取威胁指标。"""
    indicators = []
    for conn in connections:
        if not conn.get("suspicious"):
            continue
        indicators.append({
            "type": "suspicious_network",
            "value": f"{conn.get('remote_address')}:{conn.get('remote_port')} ({conn.get('process_name')})",
            "confidence": "medium",
            "entity_id": str(conn.get("pid")),  # 用于关联
            "flags": conn.get("flags", []),
        })
    return indicators


def _extract_indicators_from_logins(login_data: dict) -> List[Dict]:
    """从登录审计结果提取威胁指标。"""
    indicators = []
    details = login_data.get("suspicion_details", {})
    if details.get("brute_force"):
        for bf in details["brute_force"]:
            indicators.append({
                "type": "failed_logins_spike",
                "value": f"{bf['user']} ({bf['failures']}次失败)",
                "confidence": "high",
                "entity_id": bf.get("user", ""),
            })
    if details.get("off_hours_logins"):
        indicators.append({
            "type": "off_hours_login",
            "value": f"非工作时间登录 {details['off_hours_logins']}次",
            "confidence": "low",
            "entity_id": "",
        })
    if details.get("new_accounts"):
        indicators.append({
            "type": "new_account",
            "value": f"新创建账户 {details['new_accounts']}个",
            "confidence": "medium",
            "entity_id": "",
        })
    return indicators


def _extract_indicators_from_startup(startup_data: dict) -> List[Dict]:
    """从启动项检查结果提取威胁指标。"""
    indicators = []
    for category in ("registry_run", "scheduled_tasks", "auto_start_services", "startup_folders"):
        cat_data = startup_data.get(category, {})
        for item in cat_data.get("items", []):
            if item.get("suspicious"):
                indicators.append({
                    "type": "unsigned_startup",
                    "value": f"{item.get('name', '')} - {item.get('command', '')[:80]}",
                    "confidence": "medium",
                    "entity_id": item.get("command", ""),
                })
    return indicators


def _extract_indicators_from_registry(registry_data: dict) -> List[Dict]:
    """从注册表扫描结果提取威胁指标。"""
    indicators = []
    for finding in registry_data.get("findings", []):
        if finding.get("suspicious"):
            indicators.append({
                "type": "registry_anomaly",
                "value": f"{finding.get('path')} : {finding.get('key')} = {finding.get('value', '')[:80]}",
                "confidence": "medium",
                "entity_id": finding.get("value", ""),
            })
    return indicators


def _extract_indicators_from_files(file_data: dict) -> List[Dict]:
    """从文件完整性检查结果提取威胁指标。"""
    indicators = []
    for finding in file_data.get("findings", []):
        if finding.get("type") == "executable_in_temp":
            indicators.append({
                "type": "file_anomaly",
                "value": finding.get("path", ""),
                "confidence": "high",
                "entity_id": finding.get("path", ""),
            })
        elif finding.get("type") == "alternate_data_stream":
            indicators.append({
                "type": "file_anomaly",
                "value": f"{finding.get('path')} (ADS: {finding.get('stream')})",
                "confidence": "medium",
                "entity_id": finding.get("path", ""),
            })
    return indicators


def _extract_indicators_from_defender(defender_data: dict) -> List[Dict]:
    """从 Defender 日志检查结果提取威胁指标。"""
    indicators = []
    threats = defender_data.get("recent_threats", [])
    if isinstance(threats, list):
        for t in threats:
            indicators.append({
                "type": "defender_alert",
                "value": f"{t.get('ThreatName', '')} - {t.get('Resources', '')}",
                "confidence": "high",
                "entity_id": str(t.get("Resources", "")),
            })
    active = defender_data.get("active_threats", [])
    if isinstance(active, list):
        for t in active:
            indicators.append({
                "type": "defender_alert",
                "value": f"[ACTIVE] {t.get('ThreatName', '')}",
                "confidence": "high",
                "entity_id": "",
            })
    return indicators


def calculate_risk_score(
    forensic_results: Dict[str, Any],
    config: dict = None,
) -> Dict[str, Any]:
    """计算主机风险评分。

    Args:
        forensic_results: 各取证工具返回的数据字典，key 为工具名。
            e.g. {"scan_processes": {...}, "check_network": {...}, ...}
        config: 可选的风险评分配置，不传则从 config.yaml 加载。

    Returns:
        {
            "score": 85.0,
            "level": "高风险",
            "threat_threshold": 40,
            "is_threat": true,
            "indicators": [...],
            "breakdown": {
                "suspicious_process": {"count": 1, "score": 15},
                "suspicious_network": {"count": 1, "score": 15},
                "defender_alert": {"count": 2, "score": 50},
                "correlation_bonus": 5.0,
            },
            "details": "评分详情说明"
        }
    """
    if config is None:
        config = _load_config()

    # 1. 提取所有威胁指标
    all_indicators: List[Dict] = []

    if "scan_processes" in forensic_results:
        pd = forensic_results["scan_processes"].get("data", forensic_results["scan_processes"])
        processes = pd.get("processes", []) if isinstance(pd, dict) else []
        all_indicators.extend(_extract_indicators_from_processes(processes))

    if "check_network" in forensic_results:
        nd = forensic_results["check_network"].get("data", forensic_results["check_network"])
        connections = nd.get("connections", []) if isinstance(nd, dict) else []
        all_indicators.extend(_extract_indicators_from_network(connections))

    if "audit_logins" in forensic_results:
        ld = forensic_results["audit_logins"].get("data", forensic_results["audit_logins"])
        all_indicators.extend(_extract_indicators_from_logins(ld if isinstance(ld, dict) else {}))

    if "check_startup" in forensic_results:
        sd = forensic_results["check_startup"].get("data", forensic_results["check_startup"])
        all_indicators.extend(_extract_indicators_from_startup(sd if isinstance(sd, dict) else {}))

    if "scan_registry" in forensic_results:
        rd = forensic_results["scan_registry"].get("data", forensic_results["scan_registry"])
        all_indicators.extend(_extract_indicators_from_registry(rd if isinstance(rd, dict) else {}))

    if "check_file_integrity" in forensic_results:
        fd = forensic_results["check_file_integrity"].get("data", forensic_results["check_file_integrity"])
        all_indicators.extend(_extract_indicators_from_files(fd if isinstance(fd, dict) else {}))

    if "check_defender_logs" in forensic_results:
        dd = forensic_results["check_defender_logs"].get("data", forensic_results["check_defender_logs"])
        all_indicators.extend(_extract_indicators_from_defender(dd if isinstance(dd, dict) else {}))

    # 2. 计算基础分
    breakdown: Dict[str, Any] = {}
    base_score = 0.0
    confidence_weights = {"high": 1.0, "medium": 0.8, "low": 0.5}

    for indicator in all_indicators:
        itype = indicator["type"]
        weight = config.get(itype, 15)
        conf = indicator.get("confidence", "medium")
        adjusted = weight * confidence_weights.get(conf, 0.8)

        if itype not in breakdown:
            breakdown[itype] = {"count": 0, "score": 0.0}
        breakdown[itype]["count"] += 1
        breakdown[itype]["score"] += adjusted
        base_score += adjusted

    # 3. 关联加权：同一 entity_id 出现在多种指标中
    entity_map: Dict[str, set] = {}
    for indicator in all_indicators:
        eid = indicator.get("entity_id", "")
        if eid:
            if eid not in entity_map:
                entity_map[eid] = set()
            entity_map[eid].add(indicator["type"])

    correlation_bonus = 0.0
    for eid, types in entity_map.items():
        if len(types) >= 2:  # 同一实体触发 >=2 种指标
            # 找出该实体相关的基础分
            related_score = sum(
                config.get(t, 15) for t in types
            )
            bonus = related_score * (config.get("correlation_multiplier", 1.5) - 1.0)
            correlation_bonus += bonus
            logger.debug("Correlation: entity=%s, types=%s, bonus=%.1f", eid, types, bonus)

    breakdown["correlation_bonus"] = round(correlation_bonus, 1)

    # 4. 最终评分
    final_score = min(base_score + correlation_bonus, 100.0)
    final_score = round(final_score, 1)

    level = _get_risk_level(final_score)
    threshold = config.get("threat_threshold", 40)
    is_threat = final_score >= threshold

    # 5. 生成详情说明
    detail_parts = []
    for itype, info in breakdown.items():
        if itype == "correlation_bonus":
            if info > 0:
                detail_parts.append(f"关联加权: +{info}分")
        else:
            detail_parts.append(f"{itype}: {info['count']}个, {info['score']:.1f}分")

    return {
        "score": final_score,
        "level": level,
        "threat_threshold": threshold,
        "is_threat": is_threat,
        "total_indicators": len(all_indicators),
        "indicators": all_indicators,
        "breakdown": breakdown,
        "details": "; ".join(detail_parts),
    }


def risk_score_to_markdown(result: Dict[str, Any]) -> str:
    """将风险评分结果转为 Markdown 摘要。"""
    lines = [
        f"## 主机风险评分: {result['score']}/100 ({result['level']})",
        "",
        f"- **判定**: {'⚠ 存在威胁' if result['is_threat'] else '✓ 未发现明显威胁'}",
        f"- **威胁指标数**: {result['total_indicators']}",
        f"- **阈值**: {result['threat_threshold']}",
        "",
        "### 评分明细",
    ]
    for itype, info in result.get("breakdown", {}).items():
        if itype == "correlation_bonus":
            if info > 0:
                lines.append(f"- 关联加权: +{info}分")
        else:
            lines.append(f"- {itype}: {info['count']}个 ({info['score']:.1f}分)")

    lines.append("")
    lines.append(f"**详情**: {result.get('details', '')}")

    return "\n".join(lines)


# 便捷函数：从 AgentState 中的 collected_evidence 计算评分
def score_from_state(collected_evidence: List[Dict]) -> Dict[str, Any]:
    """从 AgentState 的 collected_evidence 直接计算风险评分。"""
    forensic_results = {}
    for evidence in collected_evidence:
        tool_name = evidence.get("tool", "")
        raw_data = evidence.get("data", {})
        if tool_name and raw_data:
            forensic_results[tool_name] = raw_data
    return calculate_risk_score(forensic_results)