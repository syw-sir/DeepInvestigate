"""
DeepInvestigate v4.0 端到端测试脚本

测试范围：
  1. 环境检查 (Python / PowerShell / Windows)
  2. 模块导入验证
  3. 单个工具单元测试（带真实 PowerShell 调用）
  4. 风险评分引擎测试（mock 数据）
  5. 完整调查流程集成测试
  6. 错误处理测试

运行方式：
  cd API
  python -m tools.forensics.test_forensics

  或管理员模式（完整测试）：
  cd API
  python -m tools.forensics.test_forensics --admin
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

# ============================================================
# 颜色输出（Windows 兼容）
# ============================================================

def _green(s: str) -> str: return f"\033[92m{s}\033[0m"
def _red(s: str) -> str: return f"\033[91m{s}\033[0m"
def _yellow(s: str) -> str: return f"\033[93m{s}\033[0m"
def _cyan(s: str) -> str: return f"\033[96m{s}\033[0m"
def _bold(s: str) -> str: return f"\033[1m{s}\033[0m"

# Windows CMD 不支持 ANSI，尝试启用
if sys.platform == "win32":
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
    except Exception:
        _green = _red = _yellow = _cyan = _bold = lambda s: s


# ============================================================
# 测试结果收集
# ============================================================

class TestReport:
    def __init__(self):
        self.results: List[Dict] = []
        self.start_time = datetime.now()

    def add(self, name: str, passed: bool, detail: str = "", duration: float = 0):
        self.results.append({
            "name": name, "passed": passed, "detail": detail, "duration": duration
        })

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r["passed"])

    @property
    def failed(self) -> int:
        return sum(1 for r in self.results if not r["passed"])

    @property
    def total(self) -> int:
        return len(self.results)

    def print_summary(self):
        elapsed = (datetime.now() - self.start_time).total_seconds()
        print()
        print("=" * 60)
        print(_bold(f"  测试报告"))
        print("=" * 60)
        for r in self.results:
            status = _green("PASS") if r["passed"] else _red("FAIL")
            time_str = f" ({r['duration']:.1f}s)" if r['duration'] > 0.1 else ""
            print(f"  [{status}] {r['name']}{time_str}")
            if r["detail"] and not r["passed"]:
                print(f"         {_red(r['detail'])}")
        print("-" * 60)
        print(f"  通过: {_green(str(self.passed))} / 失败: {_red(str(self.failed))} / 总计: {self.total}")
        print(f"  耗时: {elapsed:.1f}s")
        if self.failed == 0:
            print(f"  {_green(_bold('全部通过!'))}")
        else:
            print(f"  {_red(_bold(f'{self.failed} 项失败'))}")
        print("=" * 60)


report = TestReport()


# ============================================================
# 工具函数
# ============================================================

def run_cmd(cmd: str, timeout: int = 30) -> Tuple[bool, str]:
    """执行命令并返回 (成功, 输出)。"""
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True,
                           timeout=timeout, encoding="utf-8", errors="replace")
        output = (r.stdout + "\n" + r.stderr).strip()
        return r.returncode == 0, output[:2000]
    except subprocess.TimeoutExpired:
        return False, "TIMEOUT"
    except Exception as e:
        return False, str(e)


def is_admin() -> bool:
    """检查是否以管理员权限运行。"""
    try:
        ok, out = run_cmd("net session", timeout=5)
        return ok
    except Exception:
        return False


def check_powershell() -> Tuple[bool, str]:
    """检查 PowerShell 是否可用。"""
    ok, out = run_cmd("powershell -Command \"Write-Host 'OK'\"", timeout=10)
    return ok, out


# ============================================================
# 测试用例
# ============================================================

def test_env_check():
    """1. 环境检查"""
    print(_cyan("\n[1/6] 环境检查"))

    # Python 版本
    ver = sys.version.split()[0]
    py_ok = sys.version_info >= (3, 10)
    report.add("Python >= 3.10", py_ok, f"当前: {ver}")

    # Windows
    is_win = sys.platform == "win32"
    report.add("Windows 系统", is_win, f"平台: {sys.platform}")

    # PowerShell
    ps_ok, ps_out = check_powershell()
    report.add("PowerShell 可用", ps_ok, ps_out[:100])

    # 管理员
    admin = is_admin()
    report.add("管理员权限", admin, "部分工具需要" if not admin else "已获取")

    print(f"  Python: {_green(ver) if py_ok else _red(ver)}")
    print(f"  Windows: {_green('是') if is_win else _red('否')}")
    print(f"  PowerShell: {_green('可用') if ps_ok else _red('不可用')}")
    print(f"  管理员: {_green('是') if admin else _yellow('否 (部分测试将跳过)')}")


def test_imports():
    """2. 模块导入验证"""
    print(_cyan("\n[2/6] 模块导入"))

    modules = [
        ("tools.forensics._utils", ["run_powershell", "safe_json_parse", "format_result"]),
        ("tools.forensics.system_info", ["collect_system_info"]),
        ("tools.forensics.process_scanner", ["scan_processes"]),
        ("tools.forensics.network_monitor", ["check_network"]),
        ("tools.forensics.defender_checker", ["check_defender_logs"]),
        ("tools.forensics.login_auditor", ["audit_logins"]),
        ("tools.forensics.startup_checker", ["check_startup"]),
        ("tools.forensics.registry_scanner", ["scan_registry"]),
        ("tools.forensics.file_integrity", ["check_file_integrity"]),
        ("tools.forensics.risk_engine", ["calculate_risk_score", "risk_score_to_markdown"]),
        ("tools.registry", ["get_all_tools", "describe_tools"]),
    ]

    for mod_name, symbols in modules:
        try:
            mod = __import__(mod_name, fromlist=symbols)
            for sym in symbols:
                obj = getattr(mod, sym, None)
                assert obj is not None, f"符号 {sym} 不存在"
            report.add(f"导入 {mod_name}", True)
            print(f"  {_green('OK')} {mod_name}")
        except Exception as e:
            report.add(f"导入 {mod_name}", False, str(e))
            print(f"  {_red('FAIL')} {mod_name}: {e}")

    # 验证工具总数
    try:
        from tools.registry import get_all_tools
        all_tools = get_all_tools()
        count = len(all_tools)
        names = [t.name for t in all_tools]
        expected_forensics = {"collect_system_info", "scan_processes", "check_network",
                              "check_defender_logs", "audit_logins", "check_startup",
                              "scan_registry", "check_file_integrity"}
        actual_forensics = set(names) & expected_forensics
        all_present = actual_forensics == expected_forensics
        report.add(f"工具总数={count}, 取证工具={len(actual_forensics)}/8", all_present,
                   f"缺失: {expected_forensics - actual_forensics}" if not all_present else "")
        print(f"  工具总数: {count}, 取证工具: {len(actual_forensics)}/8 {_green('完整') if all_present else _red('缺失')}")
    except Exception as e:
        report.add("工具注册表验证", False, str(e))
        print(f"  {_red('FAIL')} 工具注册表: {e}")


def test_utils():
    """3. 公共工具函数测试"""
    print(_cyan("\n[3/6] 公共函数"))

    try:
        from tools.forensics._utils import run_powershell, safe_json_parse, format_result

        # 3.1 run_powershell 基础调用
        t0 = time.time()
        r = run_powershell("Write-Host 'hello'", timeout=10)
        dur = time.time() - t0
        ok = r["success"] and "hello" in r.get("stdout", "")
        report.add("run_powershell 基础调用", ok, str(r)[:100], dur)
        print(f"  run_powershell: {_green('OK') if ok else _red('FAIL')} ({dur:.1f}s)")

        # 3.2 safe_json_parse
        parsed = safe_json_parse('{"key": "value"}')
        ok = isinstance(parsed, dict) and parsed.get("key") == "value"
        report.add("safe_json_parse 正常JSON", ok)
        print(f"  safe_json_parse: {_green('OK') if ok else _red('FAIL')}")

        # 3.3 safe_json_parse 损坏JSON
        parsed = safe_json_parse("not json at all")
        ok = isinstance(parsed, dict) and parsed.get("parse_error") is True
        report.add("safe_json_parse 损坏JSON", ok)
        print(f"  safe_json_parse(损坏): {_green('OK') if ok else _red('FAIL')}")

        # 3.4 format_result
        result = format_result(True, data={"test": 123})
        ok = '"success": true' in result and '"test": 123' in result
        report.add("format_result", ok)
        print(f"  format_result: {_green('OK') if ok else _red('FAIL')}")

    except Exception as e:
        report.add("公共函数测试", False, str(e))
        print(f"  {_red('FAIL')}: {e}")


def test_tools_live():
    """4. 单个工具真实调用测试"""
    print(_cyan("\n[4/6] 取证工具真实调用"))

    admin = is_admin()

    # 4.1 collect_system_info (Level 0, 不需要管理员)
    try:
        from tools.forensics.system_info import collect_system_info
        t0 = time.time()
        result = collect_system_info.invoke({})
        dur = time.time() - t0
        data = json.loads(result)
        ok = data.get("success") is True
        report.add("collect_system_info", ok, str(data.get("error", ""))[:100], dur)
        print(f"  collect_system_info: {_green('OK') if ok else _red('FAIL')} ({dur:.1f}s)")
    except Exception as e:
        report.add("collect_system_info", False, str(e))
        print(f"  collect_system_info: {_red('FAIL')}: {e}")

    # 4.2 scan_processes (Level 1)
    try:
        from tools.forensics.process_scanner import scan_processes
        t0 = time.time()
        result = scan_processes.invoke({"suspicious_only": False})
        dur = time.time() - t0
        data = json.loads(result)
        ok = data.get("success") is True and "total_processes" in data.get("data", {})
        total = data.get("data", {}).get("total_processes", 0)
        suspicious = data.get("data", {}).get("suspicious_count", 0)
        report.add("scan_processes", ok, f"总进程={total}, 可疑={suspicious}", dur)
        print(f"  scan_processes: {_green('OK') if ok else _red('FAIL')} 进程={total}, 可疑={suspicious} ({dur:.1f}s)")
    except Exception as e:
        report.add("scan_processes", False, str(e))
        print(f"  scan_processes: {_red('FAIL')}: {e}")

    # 4.3 check_network (Level 1)
    try:
        from tools.forensics.network_monitor import check_network
        t0 = time.time()
        result = check_network.invoke({"established_only": False})
        dur = time.time() - t0
        data = json.loads(result)
        ok = data.get("success") is True
        total = data.get("data", {}).get("total_connections", 0)
        suspicious = data.get("data", {}).get("suspicious_count", 0)
        report.add("check_network", ok, f"连接={total}, 可疑={suspicious}", dur)
        print(f"  check_network: {_green('OK') if ok else _red('FAIL')} 连接={total}, 可疑={suspicious} ({dur:.1f}s)")
    except Exception as e:
        report.add("check_network", False, str(e))
        print(f"  check_network: {_red('FAIL')}: {e}")

    # 4.4 check_defender_logs (Level 1)
    try:
        from tools.forensics.defender_checker import check_defender_logs
        t0 = time.time()
        result = check_defender_logs.invoke({"hours_back": 24})
        dur = time.time() - t0
        data = json.loads(result)
        ok = data.get("success") is True
        enabled = data.get("data", {}).get("defender_enabled", False)
        threats = data.get("data", {}).get("total_recent_threats", 0)
        report.add("check_defender_logs", ok, f"Defender={'启用' if enabled else '未启用'}, 威胁={threats}", dur)
        print(f"  check_defender_logs: {_green('OK') if ok else _red('FAIL')} Defender={'启用' if enabled else '未启用'}, 威胁={threats} ({dur:.1f}s)")
    except Exception as e:
        report.add("check_defender_logs", False, str(e))
        print(f"  check_defender_logs: {_red('FAIL')}: {e}")

    # 4.5 check_startup (Level 1)
    try:
        from tools.forensics.startup_checker import check_startup
        t0 = time.time()
        result = check_startup.invoke({"scope": "all"})
        dur = time.time() - t0
        data = json.loads(result)
        ok = data.get("success") is True
        total = data.get("data", {}).get("total_items", 0)
        suspicious = data.get("data", {}).get("suspicious_count", 0)
        report.add("check_startup", ok, f"启动项={total}, 可疑={suspicious}", dur)
        print(f"  check_startup: {_green('OK') if ok else _red('FAIL')} 启动项={total}, 可疑={suspicious} ({dur:.1f}s)")
    except Exception as e:
        report.add("check_startup", False, str(e))
        print(f"  check_startup: {_red('FAIL')}: {e}")

    # 4.6 check_file_integrity (Level 1)
    try:
        from tools.forensics.file_integrity import check_file_integrity
        t0 = time.time()
        result = check_file_integrity.invoke({"quick": True})
        dur = time.time() - t0
        data = json.loads(result)
        ok = data.get("success") is True
        total = data.get("data", {}).get("total_findings", 0)
        high = data.get("data", {}).get("high_risk_count", 0)
        report.add("check_file_integrity", ok, f"发现={total}, 高危={high}", dur)
        print(f"  check_file_integrity: {_green('OK') if ok else _red('FAIL')} 发现={total}, 高危={high} ({dur:.1f}s)")
    except Exception as e:
        report.add("check_file_integrity", False, str(e))
        print(f"  check_file_integrity: {_red('FAIL')}: {e}")

    # 4.7 audit_logins (Level 2, 需要管理员)
    if admin:
        try:
            from tools.forensics.login_auditor import audit_logins
            t0 = time.time()
            result = audit_logins.invoke({"hours_back": 1})
            dur = time.time() - t0
            data = json.loads(result)
            ok = data.get("success") is True
            total = data.get("data", {}).get("total_events", 0)
            report.add("audit_logins (管理员)", ok, f"事件={total}", dur)
            print(f"  audit_logins: {_green('OK') if ok else _red('FAIL')} 事件={total} ({dur:.1f}s)")
        except Exception as e:
            report.add("audit_logins", False, str(e))
            print(f"  audit_logins: {_red('FAIL')}: {e}")
    else:
        report.add("audit_logins (跳过)", True, "需要管理员权限")
        print(f"  audit_logins: {_yellow('跳过 (需要管理员)')}")

    # 4.8 scan_registry (Level 2)
    try:
        from tools.forensics.registry_scanner import scan_registry
        t0 = time.time()
        result = scan_registry.invoke({"scan_type": "persistence"})
        dur = time.time() - t0
        data = json.loads(result)
        ok = data.get("success") is True
        total = data.get("data", {}).get("total_findings", 0)
        suspicious = data.get("data", {}).get("suspicious_count", 0)
        report.add("scan_registry", ok, f"发现={total}, 可疑={suspicious}", dur)
        print(f"  scan_registry: {_green('OK') if ok else _red('FAIL')} 发现={total}, 可疑={suspicious} ({dur:.1f}s)")
    except Exception as e:
        report.add("scan_registry", False, str(e))
        print(f"  scan_registry: {_red('FAIL')}: {e}")


def test_risk_engine():
    """5. 风险评分引擎测试（mock 数据）"""
    print(_cyan("\n[5/6] 风险评分引擎"))

    try:
        from tools.forensics.risk_engine import calculate_risk_score, risk_score_to_markdown

        # 5.1 正常主机（无威胁）
        clean_data = {
            "scan_processes": {
                "data": {"processes": [], "suspicious_count": 0}
            },
            "check_network": {
                "data": {"connections": [], "suspicious_count": 0}
            },
            "check_defender_logs": {
                "data": {"recent_threats": [], "active_threats": []}
            },
        }
        result = calculate_risk_score(clean_data)
        ok_clean = result["score"] == 0 and result["is_threat"] is False
        report.add("风险评分-干净主机", ok_clean, f"评分={result['score']}, 等级={result['level']}")
        print(f"  干净主机: {_green('OK') if ok_clean else _red('FAIL')} 评分={result['score']}/{result['level']}")

        # 5.2 受感染主机（多项威胁）
        infected_data = {
            "scan_processes": {
                "data": {
                    "processes": [
                        {"pid": 2844, "name": "update.exe", "suspicious": True, "suspicion_level": 3,
                         "flags": ["临时目录执行", "无数字签名", "可疑命令行: -enc"]},
                        {"pid": 1992, "name": "svch0st.exe", "suspicious": True, "suspicion_level": 1,
                         "flags": ["进程名疑似伪装"]},
                    ],
                    "suspicious_count": 2
                }
            },
            "check_network": {
                "data": {
                    "connections": [
                        {"remote_address": "45.33.32.156", "remote_port": 443, "pid": 2844,
                         "process_name": "update.exe", "state": "established", "suspicious": True,
                         "flags": ["非标准端口外联"]},
                    ],
                    "suspicious_count": 1
                }
            },
            "check_defender_logs": {
                "data": {
                    "recent_threats": [
                        {"ThreatName": "Trojan:Win32/PowerShellDownloader", "Resources": "C:\\Temp\\update.exe"},
                    ],
                    "active_threats": [],
                }
            },
            "check_startup": {
                "data": {
                    "registry_run": {
                        "items": [
                            {"name": "WindowsUpdate", "command": "C:\\Temp\\update.exe", "suspicious": True,
                             "flags": ["临时目录路径"]},
                        ]
                    },
                    "scheduled_tasks": {"items": []},
                    "auto_start_services": {"items": []},
                    "startup_folders": {"items": []},
                }
            },
        }
        result = calculate_risk_score(infected_data)
        ok_infected = result["score"] > 40 and result["is_threat"] is True
        report.add("风险评分-感染主机", ok_infected,
                   f"评分={result['score']}, 等级={result['level']}, 指标={result['total_indicators']}")
        print(f"  感染主机: {_green('OK') if ok_infected else _red('FAIL')} 评分={result['score']}/{result['level']}, 指标={result['total_indicators']}个")

        # 5.3 关联加权测试
        correlated_data = {
            "scan_processes": {
                "data": {
                    "processes": [
                        {"pid": 100, "name": "bad.exe", "suspicious": True, "suspicion_level": 2,
                         "flags": ["临时目录执行", "无数字签名"]},
                    ],
                    "suspicious_count": 1
                }
            },
            "check_network": {
                "data": {
                    "connections": [
                        {"remote_address": "10.0.0.1", "remote_port": 4444, "pid": 100,
                         "process_name": "bad.exe", "state": "established", "suspicious": True,
                         "flags": ["可疑端口"]},
                    ],
                    "suspicious_count": 1
                }
            },
            "check_startup": {
                "data": {
                    "registry_run": {
                        "items": [
                            {"name": "Updater", "command": "C:\\Temp\\bad.exe", "suspicious": True,
                             "flags": ["临时目录路径"]},
                        ]
                    },
                    "scheduled_tasks": {"items": []},
                    "auto_start_services": {"items": []},
                    "startup_folders": {"items": []},
                }
            },
            "check_defender_logs": {"data": {"recent_threats": [], "active_threats": []}},
        }
        result = calculate_risk_score(correlated_data)
        has_correlation = result.get("breakdown", {}).get("correlation_bonus", 0) > 0
        report.add("风险评分-关联加权", has_correlation,
                   f"关联加分={result.get('breakdown', {}).get('correlation_bonus', 0)}")
        print(f"  关联加权: {_green('OK') if has_correlation else _red('FAIL')} "
              f"关联加分={result.get('breakdown', {}).get('correlation_bonus', 0)}")

        # 5.4 Markdown 输出
        md = risk_score_to_markdown(result)
        ok_md = "主机风险评分" in md and "评分明细" in md
        report.add("风险评分-Markdown输出", ok_md)
        print(f"  Markdown输出: {_green('OK') if ok_md else _red('FAIL')}")

    except Exception as e:
        report.add("风险评分引擎测试", False, str(e))
        traceback.print_exc()
        print(f"  {_red('FAIL')}: {e}")


def test_error_handling():
    """6. 错误处理测试"""
    print(_cyan("\n[6/6] 错误处理"))

    try:
        from tools.forensics._utils import run_powershell, safe_json_parse

        # 6.1 无效命令超时
        r = run_powershell("Start-Sleep -Seconds 5", timeout=2)
        ok = r["error"] is not None and "超时" in r.get("error", "")
        report.add("run_powershell 超时", ok, r.get("error", ""))
        print(f"  超时处理: {_green('OK') if ok else _red('FAIL')}")

        # 6.2 空 JSON
        r = safe_json_parse("")
        ok = r.get("parse_error") is True
        report.add("safe_json_parse 空字符串", ok)
        print(f"  空JSON处理: {_green('OK') if ok else _red('FAIL')}")

        # 6.3 权限不足模拟（audit_logins 在非管理员下应有友好提示）
        if not is_admin():
            from tools.forensics.login_auditor import audit_logins
            result = audit_logins.invoke({"hours_back": 1})
            data = json.loads(result)
            # 可能成功（空结果）也可能权限错误
            has_error = not data.get("success", True) or "权限" in str(data)
            # 不是严格失败，只是确认不会崩溃
            ok = True
            report.add("audit_logins 权限不足不崩溃", ok)
            print(f"  权限不足处理: {_green('OK') if ok else _red('FAIL')} (不会崩溃)")

    except Exception as e:
        report.add("错误处理测试", False, str(e))
        print(f"  {_red('FAIL')}: {e}")


def test_integration():
    """7. 完整调查流程模拟"""
    print(_cyan("\n[7] 完整调查流程模拟"))

    try:
        # 模拟一次完整的"主机安全检查"流程
        print("  模拟: 用户请求 -> 规划 -> 采集 -> 分析 -> 评分 -> 报告")

        # Step 1: 系统信息
        from tools.forensics.system_info import collect_system_info
        sys_info = json.loads(collect_system_info.invoke({}))
        print(f"  [1/4] 系统信息采集: {_green('完成') if sys_info.get('success') else _red('失败')}")

        # Step 2: 进程 + 网络
        from tools.forensics.process_scanner import scan_processes
        from tools.forensics.network_monitor import check_network
        proc_data = json.loads(scan_processes.invoke({"suspicious_only": False}))
        net_data = json.loads(check_network.invoke({"established_only": False}))
        print(f"  [2/4] 进程+网络: 进程={proc_data.get('data',{}).get('total_processes',0)}, "
              f"连接={net_data.get('data',{}).get('total_connections',0)}")

        # Step 3: 风险评分
        from tools.forensics.risk_engine import calculate_risk_score
        forensic_results = {
            "scan_processes": proc_data,
            "check_network": net_data,
        }
        score_result = calculate_risk_score(forensic_results)
        print(f"  [3/4] 风险评分: {score_result['score']}/100 ({score_result['level']})")

        # Step 4: 报告摘要
        from tools.forensics.risk_engine import risk_score_to_markdown
        summary = risk_score_to_markdown(score_result)
        print(f"  [4/4] 报告摘要: 已生成 ({len(summary)} 字符)")

        report.add("完整调查流程模拟", True,
                   f"评分={score_result['score']}, 等级={score_result['level']}")
        print(f"  {_green('完整流程通过')}")

    except Exception as e:
        report.add("完整调查流程模拟", False, str(e))
        traceback.print_exc()
        print(f"  {_red('FAIL')}: {e}")


# ============================================================
# 主入口
# ============================================================

def main():
    print(_bold("\n" + "=" * 60))
    print(_bold("  DeepInvestigate v4.0 端到端测试"))
    print(_bold("=" * 60))
    print(f"  时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  主机: {os.environ.get('COMPUTERNAME', 'unknown')}")
    print(f"  用户: {os.environ.get('USERNAME', 'unknown')}")
    print(f"  管理员: {'是' if is_admin() else '否'}")

    # 检查是否指定了 --admin
    if "--admin" in sys.argv and not is_admin():
        print(_red("\n  --admin 模式需要以管理员身份运行!"))
        print("  请右键 -> 以管理员身份运行，或使用管理员 PowerShell")
        sys.exit(1)

    test_env_check()
    test_imports()
    test_utils()
    test_tools_live()
    test_risk_engine()
    test_error_handling()
    test_integration()

    report.print_summary()

    # 退出码
    sys.exit(0 if report.failed == 0 else 1)


if __name__ == "__main__":
    main()