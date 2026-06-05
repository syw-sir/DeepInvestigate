# DeepInvestigate v4.0 设计文档：从被动分析到自主取证

> 状态：设计阶段 | 版本：v4.0-draft | 日期：2026-06-05

---

## 目录

1. [动机与目标](#1-动机与目标)
2. [架构总览](#2-架构总览)
3. [感知层：主机取证工具集](#3-感知层主机取证工具集)
4. [AgentState 变更](#4-agentstate-变更)
5. [智能体编排变更](#5-智能体编排变更)
6. [HITL 安全审批更新](#6-hitl-安全审批更新)
7. [Critic 审查维度更新](#7-critic-审查维度更新)
8. [配置更新](#8-配置更新)
9. [实施计划](#9-实施计划)

---

## 1. 动机与目标

### 1.1 现状问题

v3.0 的系统架构设计良好（四智能体编排、HITL、Critic、记忆系统），但存在一个根本性缺陷：

```
用户："帮我查一下这台机器有没有被入侵"
系统："请把日志发给我"
```

**这和一个聊天助手没有本质区别。** 用户完全可以打开 ChatGPT，粘贴日志，获得类似的分析结果。

### 1.2 v4.0 目标

让 DeepInvestigate 成为一个 **真正自主的安全调查智能体**：

```
用户："帮我查一下这台机器有没有被入侵"
系统：自主采集进程列表、网络连接、登录日志、启动项... → 分析 → 出报告
```

**核心原则：Agent 自己去找证据，而不是等用户喂证据。**

### 1.3 设计原则

| 原则 | 说明 |
|------|------|
| **自主性** | 智能体自主决定采集什么、如何采集、何时停止 |
| **最小权限** | 取证工具默认只读，写操作需 HITL 审批 |
| **可审计** | 所有采集操作记录在案，可追溯 |
| **安全边界** | 主机命令通过白名单机制执行，禁止任意命令 |
| **向后兼容** | 不破坏现有 v3.0 架构，增量扩展 |

---

## 2. 架构总览

### 2.1 v4.0 完整闭环

```
┌─────────────────────────────────────────────────────────────┐
│                    DeepInvestigate v4.0                      │
│                                                              │
│  ┌──────────────┐   ┌──────────────────┐   ┌─────────────┐ │
│  │   感知层      │ → │    分析层         │ → │   行动层     │ │
│  │   (v4.0 新增) │   │   (v3.0 已有)     │   │ (v3.0 已有)  │ │
│  │               │   │                   │   │              │ │
│  │ • 进程枚举    │   │ • Planner         │   │ • 报告生成   │ │
│  │ • 网络连接    │   │ • Investigator    │   │ • 处置建议   │ │
│  │ • 登录审计    │   │ • Reporter        │   │ • 知识更新   │ │
│  │ • 启动项检查  │   │ • Critic          │   │              │ │
│  │ • 注册表扫描  │   │ • RAG 知识库      │   │              │ │
│  │ • 文件完整性  │   │ • 长期记忆        │   │              │ │
│  │ • 系统信息    │   │                   │   │              │ │
│  └──────────────┘   └──────────────────┘   └─────────────┘ │
│         ↑ 缺失              ↑ 已有              ↑ 已有      │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 智能体工作流（更新后）

```
START
  → retrieve_memory       (召回历史调查经验)
  → retrieve_knowledge    (RAG 检索 MITRE ATT&CK / CVE)
  → planner               (理解意图，制定调查计划)
  → investigator          (循环执行调查)
      │
      ├── [自主取证阶段] ★ NEW
      │   ├── 采集系统信息（OS版本、用户列表、补丁状态）
      │   ├── 采集安全状态（进程、网络、登录、启动项、注册表）
      │   └── 每次工具调用经过 HITL 审批
      │
      ├── [分析阶段] 已有
      │   ├── 对采集数据执行 Python 分析
      │   ├── 匹配 MITRE ATT&CK 技战术
      │   ├── 查询 CVE 漏洞
      │   └── RAG 知识库辅助研判
      │
      └── 判断 → 不够继续采集 / 够了进 reporter
          ↓
  → reporter              (整合证据，撰写报告)
  → critic                (审查报告质量)
      ├── pass → update_memory → END
      └── fail → investigator (回退补充)
```

### 2.3 模块结构

```
API/
├── agent/                    # 智能体编排（已有）
│   ├── graph.py              # ★ 更新：新增取证工具风险等级
│   ├── state.py              # ★ 更新：新增取证状态字段
│   └── nodes.py              # 不变
├── tools/                    # 工具集
│   ├── registry.py           # ★ 更新：注册新工具
│   ├── code_executor.py      # 已有
│   ├── file_io.py            # 已有
│   ├── log_query.py          # 已有
│   ├── cve_search.py         # 已有
│   ├── rag_search.py         # 已有
│   ├── recall_memory.py      # 已有
│   ├── web_search.py         # 已有
│   └── forensics/            # ★ NEW：主机取证工具包
│       ├── __init__.py
│       ├── process_scanner.py    # 进程枚举与分析
│       ├── network_monitor.py    # 网络连接检查
│       ├── login_auditor.py      # 登录审计
│       ├── startup_checker.py    # 启动项/计划任务
│       ├── registry_scanner.py   # 注册表扫描
│       ├── file_integrity.py     # 文件完整性检查
│       └── system_info.py        # 系统信息采集
├── config.yaml               # ★ 更新：取证工具配置
└── ...
```

---

## 3. 感知层：主机取证工具集

### 3.1 工具设计总则

- **所有取证工具默认只读**，不修改主机状态
- 使用 Windows 原生命令（wmic、netstat、wevtutil 等）+ Python `subprocess` 封装
- 返回结构化 JSON，便于 Investigator 分析
- 每个工具有明确的安全风险等级

**权限要求：**
- Level 0 工具：普通用户权限即可执行
- Level 1 工具：大部分普通用户可执行，部分功能（如读取其他用户进程详情）需管理员权限
- Level 2 工具（`audit_logins`, `scan_registry` 部分路径）：需要 **Administrator** 权限
- 工具在权限不足时应返回明确错误信息（如 `{"error": "权限不足，请以管理员身份运行"}`），而非崩溃

**错误处理策略：**
- 每个工具使用 try/except 包裹 subprocess 调用，捕获以下异常：
  - `PermissionError` → 返回 `{"error": "权限不足", "detail": "..."}`
  - `FileNotFoundError` → 返回 `{"error": "命令不可用", "detail": "..."}`
  - `subprocess.TimeoutExpired` → 返回 `{"error": "执行超时", "detail": "..."}`
  - `json.JSONDecodeError` → 返回原始文本 + `{"parse_error": true}`
- 编码处理：PowerShell 输出统一使用 UTF-8（`[Console]::OutputEncoding = [Text.Encoding]::UTF8`），避免 GBK/UTF-16 乱码

### 3.2 工具清单

#### 工具 1：`scan_processes` — 进程枚举与分析

| 属性 | 值 |
|------|-----|
| **风险等级** | Level 1 |
| **功能** | 枚举所有运行中的进程，提取关键信息 |
| **输入参数** | `filter_name` (可选): 进程名过滤；`suspicious_only` (可选, bool): 仅返回可疑进程 |
| **输出** | JSON 列表，每个进程包含：PID、名称、路径、命令行、父进程PID、用户、CPU/内存占用、签名状态 |

**实现方案：**
```python
# Windows: wmic process get /format:csv 或 PowerShell Get-Process
# 获取进程详情 + 签名验证
cmd = "powershell -Command \"Get-Process | Select-Object Id,ProcessName,Path,Company,CPU,WorkingSet | ConvertTo-Json\""
```

**可疑判断逻辑（Python 后处理）：**
- 进程路径在临时目录（`%TEMP%`, `%APPDATA%\Local\Temp`）
- 无数字签名的可执行文件
- 名称伪装系统进程（如 `svch0st.exe`, `1sass.exe`）
- 父进程异常（如 Office 程序启动了 PowerShell）
- 命令行包含编码/下载特征（`-enc`, `IEX`, `Invoke-`, `DownloadString`）

---

#### 工具 2：`check_network` — 网络连接检查

| 属性 | 值 |
|------|-----|
| **风险等级** | Level 1 |
| **功能** | 检查当前网络连接状态，识别可疑外联 |
| **输入参数** | `filter_port` (可选): 端口过滤；`established_only` (可选, bool): 仅显示已建立连接 |
| **输出** | JSON 列表，每个连接包含：协议、本地地址:端口、远程地址:端口、状态、关联进程PID和名称 |

**实现方案：**
```python
# Windows: netstat -ano -p tcp
# 或 PowerShell: Get-NetTCPConnection | Select-Object LocalAddress,LocalPort,RemoteAddress,RemotePort,State,OwningProcess
```

**可疑判断逻辑：**
- 连接到已知恶意 IP/域名（可结合威胁情报）
- 非标准端口上的 HTTP/HTTPS 流量（如 4444, 8080, 8443）
- 系统进程（如 svchost.exe）连接外部 IP
- 高频短连接（可能是 C2 beaconing）
- 监听端口异常（如非管理员进程监听 <1024 端口）

---

#### 工具 3：`audit_logins` — 登录审计

| 属性 | 值 |
|------|-----|
| **风险等级** | Level 2 |
| **功能** | 审计 Windows 安全事件日志中的登录事件 |
| **输入参数** | `hours_back` (默认 24): 回溯小时数；`event_types` (可选): 事件ID过滤 |
| **输出** | JSON 列表，包含：时间、事件ID、用户、来源IP、登录类型、结果（成功/失败） |

**关键事件 ID：**
| Event ID | 含义 |
|----------|------|
| 4624 | 登录成功 |
| 4625 | 登录失败 |
| 4648 | 显式凭据登录 |
| 4672 | 特权分配 |
| 4776 | NTLM 认证 |

**实现方案：**
```python
# wevtutil qe Security /q:"*[System[EventID=4624 or EventID=4625]]" /f:json /c:100
# 或 PowerShell Get-WinEvent
```

**可疑判断逻辑：**
- 短时间内大量失败登录（暴力破解）
- 非工作时间的管理员登录
- 来自外部 IP 的 RDP 登录（EventID 4624, LogonType=10）
- 服务账户交互式登录（异常）
- 新增本地账户创建（EventID 4720）

---

#### 工具 4：`check_startup` — 启动项/计划任务检查

| 属性 | 值 |
|------|-----|
| **风险等级** | Level 1 |
| **功能** | 检查系统启动项、计划任务，发现持久化后门 |
| **输入参数** | `scope` (可选): "all" / "registry" / "tasks" / "services" |
| **输出** | JSON，按类别分组：注册表Run键、计划任务、服务、启动文件夹 |

**检查位置：**
```
注册表 Run 键:
  HKLM\Software\Microsoft\Windows\CurrentVersion\Run
  HKCU\Software\Microsoft\Windows\CurrentVersion\Run
  HKLM\Software\Microsoft\Windows\CurrentVersion\RunOnce

计划任务:
  schtasks /query /fo csv /v

服务:
  非 Microsoft 签名的自动启动服务

启动文件夹:
  %APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup
  %PROGRAMDATA%\Microsoft\Windows\Start Menu\Programs\Startup
```

**可疑判断逻辑：**
- 启动项指向临时目录或用户目录
- 无签名的可执行文件
- 计划任务触发器异常（如每小时执行）
- 服务名伪装系统服务
- 命令行包含编码/混淆内容

---

#### 工具 5：`scan_registry` — 注册表可疑项扫描

| 属性 | 值 |
|------|-----|
| **风险等级** | Level 2 |
| **功能** | 扫描注册表中的常见恶意软件驻留位置 |
| **输入参数** | `scan_type` (可选): "persistence" / "uac_bypass" / "appinit" / "all" |
| **输出** | JSON，每个可疑项包含：路径、键名、值、风险说明 |

**扫描位置：**

| 类别 | 注册表路径 | 攻击技术 |
|------|-----------|---------|
| AppInit_DLLs | `HKLM\Software\Microsoft\Windows NT\CurrentVersion\Windows\AppInit_DLLs` | DLL 注入 |
| Image File Execution | `HKLM\Software\Microsoft\Windows NT\CurrentVersion\Image File Execution Options\*` | 进程劫持 |
| Winlogon Shell | `HKLM\Software\Microsoft\Windows NT\CurrentVersion\Winlogon\Shell` | 后门 |
| LSA Provider | `HKLM\System\CurrentControlSet\Control\Lsa\*` | 凭据窃取 |
| Browser Helper | `HKLM\Software\Microsoft\Windows\CurrentVersion\Explorer\Browser Helper Objects\*` | 浏览器劫持 |
| WMI Persistence | `HKLM\Software\Microsoft\WBEM\*` | WMI 持久化 |

---

#### 工具 6：`check_file_integrity` — 文件完整性检查

| 属性 | 值 |
|------|-----|
| **风险等级** | Level 1 |
| **功能** | 检查关键系统文件是否被篡改，扫描可疑文件 |
| **输入参数** | `path` (可选): 指定扫描路径；`quick` (可选, bool): 快速模式仅检查关键目录 |
| **输出** | JSON，包含：新创建文件、最近修改文件、隐藏文件、异常权限文件 |

**检查内容：**
- `C:\Windows\System32\` 下最近 7 天新增/修改的可执行文件
- `C:\Windows\Temp\` 和 `%TEMP%` 下的可执行文件（高度可疑）
- 隐藏文件和 Alternate Data Streams (ADS)
- 关键系统 DLL 文件哈希计算（`Get-FileHash`，只读验证，不修改文件）

**实现方案：**
```python
# PowerShell 查找最近修改的文件
# Get-ChildItem -Path C:\Windows\System32\*.exe | Where-Object {$_.LastWriteTime -gt (Get-Date).AddDays(-7)}
# 文件哈希计算（只读）：Get-FileHash -Algorithm SHA256 <path>
# 注意：不使用 sfc /scannow（它会修改/替换系统文件，违反只读原则）
```

---

#### 工具 7：`collect_system_info` — 系统信息采集

| 属性 | 值 |
|------|-----|
| **风险等级** | Level 0 |
| **功能** | 采集主机基本信息，为调查提供上下文 |
| **输入参数** | 无 |
| **输出** | JSON，包含：OS版本、补丁级别、用户列表、组信息、防火墙状态、杀软状态、环境变量 |

**采集内容：**
- OS 版本与 Build 号
- 已安装的补丁（最近 10 个）
- 本地用户和组成员
- Windows Defender / 第三方杀软状态
- 防火墙规则概要
- 系统环境变量（PATH 等）

---

#### 工具 8：`check_defender_logs` — Windows Defender 告警检查

| 属性 | 值 |
|------|-----|
| **风险等级** | Level 1 |
| **功能** | 查询 Windows Defender 的历史检测记录和当前状态 |
| **输入参数** | `hours_back` (默认 168): 回溯小时数 |
| **输出** | JSON，包含：Defender 状态、最近威胁检测记录、隔离文件列表 |

**采集内容：**
- Windows Defender 运行状态（是否启用、是否最新）
- 最近检测到的威胁（威胁名称、文件路径、处置结果）
- 隔离区文件列表
- 排除项配置（攻击者可能添加排除路径）

**实现方案：**
```powershell
# 获取 Defender 状态
Get-MpComputerStatus | Select-Object AntivirusEnabled,RealTimeProtectionEnabled,LastFullScanTime

# 获取威胁检测历史
Get-MpThreatDetection | Select-Object InitialDetectionTime,ThreatName,Resources,ActionSuccess

# 获取隔离项
Get-MpThreat | Select-Object ThreatName,ThreatStatus,IsActive
```

---

### 3.3 工具注册

在 `tools/registry.py` 中新增导入和注册：

```python
from .forensics.process_scanner import scan_processes
from .forensics.network_monitor import check_network
from .forensics.login_auditor import audit_logins
from .forensics.startup_checker import check_startup
from .forensics.registry_scanner import scan_registry
from .forensics.file_integrity import check_file_integrity
from .forensics.system_info import collect_system_info
from .forensics.defender_checker import check_defender_logs

_ALL_TOOLS = [
    # 原有工具
    run_python, read_file, write_file, list_files,
    query_logs, search_cve, rag_search, recall_memory, web_search,
    # v4.0 取证工具
    scan_processes,
    check_network,
    audit_logins,
    check_startup,
    scan_registry,
    check_file_integrity,
    collect_system_info,
    check_defender_logs,
]
```

### 3.4 工具风险等级总表

| 工具 | 等级 | 原因 |
|------|------|------|
| `collect_system_info` | Level 0 | 纯信息采集，无安全风险 |
| `scan_processes` | Level 1 | 读取进程信息，不修改 |
| `check_network` | Level 1 | 读取网络状态，不修改 |
| `check_startup` | Level 1 | 读取注册表/任务，不修改 |
| `check_file_integrity` | Level 1 | 文件扫描，不修改 |
| `check_defender_logs` | Level 1 | 读取 Defender 日志，不修改 |
| `audit_logins` | Level 2 | 读取安全日志，可能触发审计 |
| `scan_registry` | Level 2 | 读取敏感注册表位置 |

---

## 4. AgentState 变更

在 `agent/state.py` 中新增取证相关字段：

```python
class AgentState(TypedDict, total=False):
    # ... 原有字段保持不变 ...

    # ---- v4.0: 自主取证 ----
    forensic_phase: str                    # 取证阶段: "initial" / "deep" / "complete"
    collected_evidence: List[Dict]         # 已采集的原始证据（最多保留 20 条，超出后自动截断最旧的）
    evidence_summary: Optional[str]        # 证据摘要（由 Investigator 在采集足够后生成）
    threat_indicators: List[Dict]          # 威胁指标 [{type, value, confidence, mitre_id}]
    mitre_mappings: List[Dict]             # MITRE ATT&CK 技战术映射
    risk_score: Optional[float]            # 主机风险评分 (0-100)

    # 注意：不新增 forensic_plan 字段。取证计划复用现有 plan 字段（List[str]），
    # Planner 在计划中直接包含取证步骤即可，如 "1. collect_system_info: 了解主机环境"
```

**证据管理策略：**
- `collected_evidence` 最多保留 **20 条**记录，超出后自动截断最旧条目
- 每条证据包含：`{tool, timestamp, summary (≤200字), key_findings (≤3条), raw_size}`
- 原始大数据不放入 state，而是写入 workspace 临时文件，证据中仅记录文件路径
- 这样既保证 Critic 可以审查证据链，又不会让 state 无限膨胀

---

## 5. 智能体编排变更

### 5.1 Planner 增强

**Planner 系统提示词新增：**

```
你是一位主机安全调查规划专家。当用户请求主机安全调查时，你需要制定自主取证计划。

## 取证策略

### 第一层：快速扫描（优先执行）
1. collect_system_info — 了解主机基本环境
2. scan_processes — 检查可疑进程
3. check_network — 检查可疑网络连接

### 第二层：深度检查（基于第一层发现）
4. check_startup — 持久化检查
5. check_file_integrity — 文件完整性
6. audit_logins — 登录审计（如发现异常进程/连接）

### 第三层：专项扫描（基于前两层发现）
7. scan_registry — 注册表深度扫描
8. 对采集数据执行 Python 分析
9. search_cve — 漏洞关联查询

## 计划制定规则
- 每个步骤指定：工具名、调用原因、预期输出、优先级
- 步骤之间可以有依赖关系（先用 A 工具采集，再根据结果决定用 B）
- 不需要一次规划所有步骤，先规划第一层，后续根据结果动态调整
```

### 5.2 Investigator 增强

**Investigator 系统提示词新增：**

```
你是一位主机安全调查执行专家。你可以自主使用取证工具采集主机信息，然后分析判断。

## 自主调查规则

1. **主动采集**：不要等用户提供数据。根据调查计划，主动调用取证工具采集信息。
2. **证据驱动**：每个结论必须有工具输出支撑。引用具体的 PID、IP、文件路径、时间戳。
3. **渐进深入**：先用轻量工具（system_info, processes, network），发现异常后再用深度工具。
4. **威胁研判**：结合 MITRE ATT&CK 知识，判断采集到的指标是否构成真实威胁。
5. **适时停止**：当证据足够支撑结论时，不要无限制采集。如果采集 3 轮仍未发现异常，可以给出"未发现威胁"的结论。

## 工具选择策略

| 发现 | 下一步 |
|------|--------|
| 可疑进程 | 检查该进程的网络连接、文件路径、启动项、签名 |
| 可疑网络连接 | 追踪关联进程、检查计划任务持久化 |
| 大量登录失败 | 审计安全日志、检查新增账户 |
| 异常注册表项 | 关联进程和文件检查 |
| 系统信息显示未打补丁 | 查询相关 CVE 漏洞 |
```

---

## 6. HITL 安全审批更新

在 `graph.py` 中更新 `TOOL_RISK_LEVELS`：

```python
TOOL_RISK_LEVELS = {
    # 原有工具
    "rag_search":      0,
    "recall_memory":   0,
    "list_files":      0,
    "read_file":       0,
    "run_python":      1,
    "write_file":      1,
    "web_search":      1,
    "query_logs":      2,
    "search_cve":      2,

    # v4.0 取证工具
    "collect_system_info":  0,
    "scan_processes":       1,
    "check_network":        1,
    "check_startup":        1,
    "check_file_integrity": 1,
    "audit_logins":         2,
    "scan_registry":        2,
}
```

### 审批粒度优化

新增 **会话级信任** 机制：

- 用户批准某个 Level 1 工具后，可选择"本次会话不再询问同类工具"
- 通过 `_approval_result` 中的 `session_trust` 字段控制

```python
# HITL 审批结果扩展
{
    "approved": true,
    "tool_name": "scan_processes",
    "session_trust": true,      # ★ 新增：本次会话信任同类工具
    "trusted_tools": ["scan_processes", "check_network", ...],
}
```

---

## 7. Critic 审查维度更新

Critic 系统提示词新增取证相关审查维度：

```
## 审查维度（每项 1-5 分）

1. **事实准确性**：报告中的结论是否有取证工具输出支撑？有无凭空捏造？
2. **逻辑完整性**：调查过程是否覆盖了所有计划步骤？有无遗漏关键环节？
3. **证据充分性** ★ NEW：每个威胁结论是否有至少一个取证工具输出作为证据？
4. **信息完整度**：是否遗漏了重要的攻击指标（PID、IP、文件路径、时间戳）？
5. **建议可行性**：处置建议是否具体、可操作？是否包含具体命令或操作步骤？

## 特别审查项 ★ NEW
- 报告中的 IP/PID/文件路径是否能在工具输出中找到原始记录？
- 威胁判定是否有 MITRE ATT&CK 技战术映射？
- 风险评分是否有评分依据说明？
```

---

## 8. 配置更新

在 `config.yaml` 中新增取证配置段：

```yaml
# v4.0: 自主取证配置
forensics:
  enabled: true

  # 命令白名单（主机端执行的命令，不在白名单中的拒绝执行）
  command_whitelist:
    - "wmic"
    - "netstat"
    - "wevtutil"
    - "schtasks"
    - "powershell"
    - "sc"
    - "reg"
    - "icacls"

  # 扫描限制
  limits:
    max_processes: 500        # 单次扫描最大进程数
    max_network_conns: 1000   # 单次扫描最大连接数
    max_log_events: 500       # 单次查询最大日志条数
    file_scan_max_depth: 3    # 文件扫描目录深度
    file_scan_timeout: 120    # 文件扫描超时（秒）

  # 风险评分权重（注意：同一实体的多项指标会触发关联加权）
  risk_scoring:
    # 基础分
    suspicious_process: 15    # 每个可疑进程 +15 分
    suspicious_network: 15    # 每个可疑连接 +15 分
    failed_logins_spike: 20   # 暴力破解特征 +20 分
    unsigned_startup: 20      # 未签名启动项 +20 分
    registry_anomaly: 15      # 注册表异常 +15 分
    file_anomaly: 15          # 文件异常 +15 分
    defender_alert: 25        # Defender 已有告警 +25 分（高权重）
    # 关联加权：同一实体（如同一个 PID）同时触发进程+网络+启动项 → 额外 ×1.5
    correlation_multiplier: 1.5
    threat_threshold: 40      # 评分 >= 40 判定为"存在威胁"

  # 可疑指标规则（可热更新）
  indicators:
    suspicious_paths:
      - "%TEMP%"
      - "%APPDATA%\\Local\\Temp"
      - "C:\\Users\\Public"
      - "C:\\ProgramData\\Temp"
    suspicious_parents:
      - "winword.exe"
      - "excel.exe"
      - "outlook.exe"
      - "wscript.exe"
      - "mshta.exe"
    suspicious_cmd_keywords:
      - "-enc"
      - "-EncodedCommand"
      - "IEX"
      - "Invoke-Expression"
      - "Invoke-WebRequest"
      - "DownloadString"
      - "FromBase64String"
      - "Net.WebClient"
      - "Start-Process -WindowStyle Hidden"

  # 已知恶意 IP/域名列表（可对接威胁情报API）
  threat_intel:
    enabled: false
    api_url: ""
    api_key: ""
```

---

## 9. 实施计划

### Phase 1：基础取证工具（核心）

**预计工作量：3-4 天**

| 序号 | 任务 | 文件 | 说明 |
|------|------|------|------|
| 1.1 | `collect_system_info` | `tools/forensics/system_info.py` | 系统信息采集 |
| 1.2 | `scan_processes` | `tools/forensics/process_scanner.py` | 进程枚举 + 可疑判断 |
| 1.3 | `check_network` | `tools/forensics/network_monitor.py` | 网络连接检查 |
| 1.4 | 工具注册更新 | `tools/registry.py` | 注册新工具到注册表 |
| 1.5 | HITL 风险等级更新 | `agent/graph.py` | 新增工具风险等级 |
| 1.6 | AgentState 更新 | `agent/state.py` | 新增取证状态字段 |
| 1.7 | 配置文件更新 | `config.yaml` | 取证配置段 |

### Phase 2：深度取证工具

**预计工作量：2-3 天**

| 序号 | 任务 | 文件 | 说明 |
|------|------|------|------|
| 2.1 | `audit_logins` | `tools/forensics/login_auditor.py` | 登录审计 |
| 2.2 | `check_startup` | `tools/forensics/startup_checker.py` | 启动项检查 |
| 2.3 | `scan_registry` | `tools/forensics/registry_scanner.py` | 注册表扫描 |
| 2.4 | `check_file_integrity` | `tools/forensics/file_integrity.py` | 文件完整性检查 |

### Phase 3：智能体集成

**预计工作量：2-3 天**

| 序号 | 任务 | 说明 |
|------|------|------|
| 3.1 | Planner 提示词更新 | 新增取证策略 |
| 3.2 | Investigator 提示词更新 | 新增自主调查规则 |
| 3.3 | Critic 提示词更新 | 新增取证证据审查 |
| 3.4 | 风险评分引擎 | `tools/forensics/risk_engine.py` — 根据采集结果计算主机风险评分 |
| 3.5 | 端到端测试 | 在 Windows 环境测试完整调查流程 |

### Phase 4：增强（可选）

| 序号 | 任务 | 说明 |
|------|------|------|
| 4.1 | 威胁情报集成 | 对接 VirusTotal / AbuseIPDB 等 API |
| 4.2 | 内存取证 | 集成 Volatility（需要更高权限） |
| 4.3 | YARA 规则扫描 | 文件特征匹配 |
| 4.4 | 实时监控 | 文件系统/注册表变更监控 |
| 4.5 | 处置能力 | 隔离进程、删除文件、阻断连接（需要 HITL 最高级审批） |

---

## 附录 A：与 v3.0 的兼容性

| v3.0 组件 | v4.0 变更 | 兼容性 |
|-----------|----------|--------|
| `graph.py` | 新增风险等级条目 | 向后兼容，纯增量 |
| `state.py` | 新增可选字段 | 向后兼容，TypedDict total=False |
| `registry.py` | 新增导入和工具列表 | 向后兼容 |
| `config.yaml` | 新增 forensics 段 | 向后兼容 |
| `nodes.py` | 提示词更新 | 向后兼容，行为增强 |
| 前端 | 审批 UI 显示新工具 | 无需变更，协议不变 |

---

## 附录 B：端到端使用示例

```
用户输入：帮我检查这台主机有没有被入侵

Planner 制定计划：
  1. collect_system_info   → 了解主机环境
  2. scan_processes        → 检查可疑进程
  3. check_network         → 检查可疑网络连接
  4. [根据结果决定后续步骤]

Investigator 执行：
  Step 1: collect_system_info()
    → Windows 10 22H2, 补丁 KB5021234, 用户: admin, guest

  Step 2: scan_processes(suspicious_only=true)
    → 发现进程 PID 2844: C:\Users\admin\AppData\Local\Temp\update.exe
      无签名, 父进程 wscript.exe, 命令行包含 "-enc SQBFAFgAIAAoAE4AZ..."
      可疑度: 高

  Step 3: check_network(filter_pid=2844)
    → 进程 2844 连接到 45.33.32.156:443 (ESTABLISHED)
      该 IP 归属: DigitalOcean (非业务相关)

  Step 4: check_startup()
    → 注册表 Run 键发现:
      HKCU\...\Run\WindowsUpdate = C:\Users\admin\AppData\Local\Temp\update.exe
      该启动项无数字签名, 路径在临时目录

  Step 5: search_cve(query="CVE-2024-...")
    → 结合系统补丁状态判断是否存在可利用漏洞

  Step 6: run_python(分析代码)
    → 解码 Base64 命令行: "IEX (New-Object Net.WebClient).DownloadString(...)"
    → 确认是 PowerShell 下载器

Reporter 生成报告：
  ## 调查结论：主机已被入侵

  ### 威胁指标
  | 类型 | 值 | 置信度 |
  |------|-----|--------|
  | 恶意进程 | PID 2844 update.exe | 高 |
  | C2 通信 | 45.33.32.156:443 | 高 |
  | 持久化 | HKCU Run 键 | 高 |

  ### MITRE ATT&CK 映射
  - T1059.001: PowerShell
  - T1140: 编码混淆
  - T1547.001: 注册表 Run 键持久化
  - T1071.001: HTTPS C2

  ### 风险评分: 85/100 (高风险)

  ### 处置建议
  1. 立即断网隔离主机
  2. 终止进程 PID 2844: taskkill /PID 2844 /F
  3. 删除注册表 Run 键
  4. 删除文件: C:\Users\admin\AppData\Local\Temp\update.exe
  5. 全盘杀毒扫描
  6. 排查初始入侵途径（补丁状态、钓鱼邮件等）

Critic 审查：
  评分: 5/5 通过
  理由: 证据充分，逻辑完整，建议可执行
```