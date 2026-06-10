# DeepInvestigate v4.1

> **基于 LangGraph 的自主取证多智能体安全调查与处置系统**：感知 → 分析 → 行动 → 回滚完整闭环，自己采集证据、自己分析研判、自己处置威胁、支持一键回滚。

## 项目简介

DeepInvestigate 是一个**真正自主的安全调查与处置智能体**——不是等用户喂数据，而是自己调用取证工具采集主机信息，通过四 Agent 协作完成分析研判，发现威胁后可以自动处置（终止进程、隔离文件、封禁 IP 等），每个处置操作都有备份支持回滚。

**与聊天助手的本质区别：** 你说"帮我查这台机器有没有被入侵，有威胁就处理掉"，它自己动手查、自己动手修，而不是说"请把日志发给我"。

### v4.1 核心能力

- **自主取证引擎 (v4.0)**：8 个主机取证工具，自主采集进程、网络、登录、启动项、注册表、文件、Defender 日志等
- **自动处置闭环 (v4.1 NEW)**：6 个处置工具（kill_process / quarantine_file / block_ip / remove_startup / repair_registry / rollback_action），每个操作前自动备份，支持一键回滚
- **多 Agent 编排**：基于 **LangGraph** 的 `Planner → Investigator → Reporter → Critic` 四 Agent 协作 + 闲聊快捷路由
- **风险评分引擎**：0-100 分量化评估，关联加权算法，MITRE ATT&CK 技战术映射
- **前端 HITL 审批 UI (NEW)**：处置工具（Level 3）调用时前端弹出交互式审批卡片，带批准/拒绝按钮，点击后通过 `/chat/resume` 恢复执行
- **非管理员优雅降级 (NEW)**：取证工具在无管理员权限时自动回退（Get-NetTCPConnection → netstat -ano，Get-Process 去 -IncludeUserName），保证普通用户下调查流程可用
- **Checkpointing**：SQLite 持久化，支持会话恢复与时间旅行调试
- **Critic 自审查**：7 维评分（v4.1 新增证据充分性、处置安全性、处置完整性），不合格自动回退补充调查
- **多模型路由**：按节点分配模型，主模型不可用时自动 fallback，Token 成本追踪
- **MCP 协议**：工具封装为 MCP Server，跨项目/跨框架复用
- **安全护栏**：输入敏感词拦截 + 输出 PII 脱敏 + 审计日志
- **23 个工具**：9 个分析工具 + 8 个取证工具 + 6 个处置工具，通过 OpenAI Function Calling 标准协议调用
- **RAG 检索增强**：ChromaDB + OpenAI Embedding + MITRE ATT&CK / CVE 知识库
- **多层长期记忆**：基于 Redis Stack 的四层记忆 + Mem0
- **可观测 + 可评估**：LangSmith 全链路追踪 + 自研 10 指标评估体系 + 端到端测试脚本

---

## 快速开始

### 系统要求

- Python 3.10+
- Node.js 16+
- Windows 10/11（取证工具依赖 PowerShell）
- 推荐使用 conda 环境管理工具

### 安装步骤

1. **启动基础设施**
   ```bash
   # Redis Stack + ChromaDB
   docker compose up -d
   ```

2. **安装 Python 依赖**
   ```bash
   conda create -n DeepInvestigate python=3.10 -y
   conda activate DeepInvestigate
   pip install -r requirements.txt
   pip install -r requirements-v2.txt
   ```

3. **灌入种子知识库（首次）**
   ```bash
   cd API
   python -m rag.ingest --dir ../knowledge
   cd ..
   ```

4. **安装前端依赖**
   ```bash
   cd demo/chat/frontend
   npm install
   cd ../../..
   ```

5. **配置 API 密钥**
   - 编辑 `API/config.yaml`，填写 DeepSeek API 密钥
   - 可选：填入 `langsmith.api_key` 启用全链路追踪

### 运行服务

#### Windows（推荐以管理员身份运行后端以获得完整处置能力）

```bash
# 一键启动（非管理员）
.\start_all_v2.bat

# 或以管理员身份手动启动后端：
# 右键 PowerShell → 以管理员身份运行
cd API
python server_v2.py

# 另一个终端启动前端：
cd demo\chat\frontend
npm run dev
```

> **权限说明**：非管理员运行时，8 个取证工具中的 5 个完全可用，3 个部分受限；6 个处置工具需要管理员权限才能执行。系统会自动回退到兼容方案并给出友好提示。

### 访问服务

- **前端界面**：http://localhost:4000
- **后端 API**：http://localhost:8201
- **文件服务**：http://localhost:8101
- **RedisInsight**：http://localhost:8001 （记忆数据可视化）

---

## 端到端测试

验证所有取证工具是否正常工作：

```bash
# 普通模式（跳过需要管理员权限的测试）
cd API
python -m tools.forensics.test_forensics

# 管理员模式（完整测试，包括安全日志审计）
# 右键 PowerShell -> 以管理员身份运行
cd API
python -m tools.forensics.test_forensics --admin
```

测试覆盖：环境检查、模块导入、8 个取证工具真实调用、风险评分引擎、错误处理、完整调查流程模拟。

---

## 使用方法

### 主机安全调查与处置（v4.1 核心场景）

1. **输入调查指令**：在聊天框中输入"帮我检查这台主机有没有安全隐患"
2. **系统自主取证**：Planner 制定计划，Investigator 自主调用 8 个取证工具采集证据
3. **智能分析研判**：结合 MITRE ATT&CK 知识库，对采集数据进行威胁研判，输出风险评分
4. **HITL 审批处置**：如需处置威胁，前端弹出审批卡片（显示工具名、风险等级），你点批准后执行
5. **生成调查报告**：包含 IoC 指标、风险评分、MITRE 技战术映射、处置建议和回滚 ID

### 其他使用场景

1. **威胁处置**："帮我终止 PID 1234 的恶意进程" / "封禁 IP 1.2.3.4"
2. **日志分析**：上传日志文件，系统自动结构化查询和分析
3. **漏洞评估**：查询 CVE 漏洞信息，评估主机补丁状态
4. **知识问答**：利用内置 MITRE ATT&CK / CVE 知识库回答问题
5. **下载报告**：分析完成后，可以下载生成的报告文件

---

## 架构（v4.1）

```
┌──────────────────────────────────────────────────────────────┐
│        前端 (Next.js 14 + shadcn/ui)        :4000            │
│        + HITL 审批卡片 + 批准/拒绝按钮 + 用量面板              │
└──────────────────────────────────────────────────────────────┘
                       │ SSE 流式 + HITL /chat/resume
┌──────────────────────────────────────────────────────────────┐
│        API 层 (FastAPI)                     :8201            │
│        + /chat/resume + /threads/{id}/history + /admin/usage │
└──────────────────────────────────────────────────────────────┘
                       │
┌──────────────────────────────────────────────────────────────┐
│        Agent 编排层 (LangGraph + Checkpointer)               │
│   ┌─────────┐  ┌──────────────┐  ┌────────┐  ┌────────┐     │
│   │ Planner │->│ Investigator │->│Reporter│->│ Critic │     │
│   └─────────┘  └──────┬───────┘  └────────┘  └───┬────┘     │
│        ↑              ┌────┴─────────────┐    ┌──┴──────┐    │
│   chat_responder      ▼                  ▼    ▼         ▼    │
│   (闲聊快捷路由)  ┌──────────┐    ┌────────────┐ ┌──────┐    │
│                  │23 Tools  │    │  Forensics  │ │ HITL │    │
│                  │(9+8+6)   │    │  (8+6 v4.1) │ │ L3   │    │
│                  └──────────┘    └────────────┘ └──────┘    │
│                  ┌──────────┐    ┌────────────┐ ┌──────┐    │
│                  │  Memory  │    │Risk Engine │ │Guard │    │
│                  │ 4 layers │    │ (0-100分)  │ │rails │    │
│                  └──────────┘    └────────────┘ └──────┘    │
│                  ┌──────────┐                                │
│                  │ Rollback │  ← v4.1 处置回滚               │
│                  └──────────┘                                │
└──────────────────────────────────────────────────────────────┘
                       │
       ┌───────────────┼───────────────┬────────────────┐
       ▼               ▼               ▼                ▼
┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐
│ Redis Stack │ │  ChromaDB   │ │ LangSmith   │ │ Model Router│
│ (4 类记忆 + │ │ (RAG 知识库) │ │ (全链路追踪) │ │ (多模型降级) │
│  HNSW 向量) │ │             │ │             │ │             │
└─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘
```

### LangGraph 节点流程 (v4.1)

```
START
  ├── _is_chat_question? ── YES → chat_responder → END  (闲聊快捷路由)
  └── NO
        ↓
  retrieve_memory → retrieve_knowledge → planner
                                            ↓
                                      investigator ←──────────────┐
                                        ↓                         │
                                  [v4.0 自主取证]                  │
                                  collect_system_info              │
                                  scan_processes                   │
                                  check_network                    │
                                  check_defender_logs              │
                                  audit_logins                     │
                                  check_startup                    │
                                  scan_registry                    │
                                  check_file_integrity             │
                                        ↓                         │
                                  [v4.1 威胁处置]                  │
                                  kill_process                     │
                                  quarantine_file                  │
                                  block_ip                         │
                                  remove_startup                   │
                                  repair_registry                  │
                                  rollback_action                  │
                                        ↓                         │
                                  [human_approval] ← HITL (L3)     │
                                        ↓                         │
                                  tool_executor ──────────────────┘
                                        ↓
                                      reporter
                                        ↓
                                    critic (7维评分)
                                     /       \
                                (pass)     (fail → investigator)
                                    ↓
                              update_memory → END
```

---

## 工具清单

### v4.0 取证工具（8 个）

| 工具 | 风险 | 功能 | 非管理员 |
|------|:--:|------|:--:|
| `collect_system_info` | 0 | OS 版本、用户、防火墙、Defender 状态 | ✅ |
| `scan_processes` | 1 | 进程枚举 + 可疑分析（伪装检测、临时目录执行） | ✅ |
| `check_network` | 1 | 网络连接 + 可疑外联识别、监听端口分析 | ✅ (netstat回退) |
| `check_defender_logs` | 1 | Defender 告警历史和当前状态 | ⚠️ 部分受限 |
| `check_startup` | 1 | 注册表 Run 键、计划任务、自启服务 | ✅ |
| `check_file_integrity` | 1 | 临时目录可执行文件、ADS 检测 | ⚠️ 部分受限 |
| `audit_logins` | 2 | 安全事件日志审计（暴力破解、RDP 异常） | ❌ 需管理员 |
| `scan_registry` | 2 | 注册表可疑项（IFEO 劫持、Winlogon、浏览器劫持） | ✅ |

### v4.1 处置工具（6 个）

| 工具 | 风险 | 功能 | 备份方式 |
|------|:--:|------|---------|
| `kill_process` | 3 | 终止恶意进程 | 进程信息 JSON |
| `quarantine_file` | 3 | 隔离可疑文件（SHA256 备份） | 文件副本 |
| `block_ip` | 3 | 添加防火墙规则封禁 IP | 规则名记录 |
| `remove_startup` | 3 | 清除恶意启动项（注册表/计划任务/服务） | .reg / .xml 导出 |
| `repair_registry` | 3 | 修复注册表异常项 | .reg 导出 |
| `rollback_action` | 2 | 回滚任意处置操作 | 从备份恢复 |

> **HITL 审批**：Level 3 处置工具执行前自动暂停，前端弹审批卡片。Level 0-2 工具自动放行。处置工具推荐以管理员身份运行后端。

---

## 技术栈

| 类别 | 技术 |
|---|---|
| **Agent 框架** | LangGraph · LangChain · Checkpointer (SQLite) |
| **模型** | DeepSeek · OpenAI (多模型路由 + fallback) |
| **Embedding** | OpenAI Embeddings / BGE-M3 (可切换) |
| **向量库** | ChromaDB（知识库） + RediSearch HNSW（记忆） |
| **长期记忆** | Redis Stack 4 层（工作 / 情景 / 语义 / 程序） + Mem0 |
| **后端** | FastAPI · Uvicorn · SSE 流式 · async/await |
| **前端** | Next.js 14 · React 18 · TypeScript 5 · shadcn/ui · Tailwind CSS |
| **HITL** | LangGraph interrupt() + 前端审批卡片 UI + /chat/resume |
| **安全** | 输入护栏 · 输出 PII 脱敏 · 工具三级风险 · subprocess 安全策略 · 处置白名单 |
| **v4.0 取证** | PowerShell Automation · netstat · Get-Process · Get-Service · Get-ScheduledTask |
| **v4.1 处置** | taskkill · netsh advfirewall · reg export/import · schtasks · sc · 自动备份回滚 |
| **可观测性** | LangSmith · 结构化日志 · Token 成本追踪 |
| **评估** | 自研 10 指标评估体系 · 50+ 测试集 · 端到端测试脚本 |
| **协议** | OpenAI Function Calling · MCP · A2A (Agent-to-Agent) |

---

## 项目结构

```
deepinvestigate_3.0/
├── API/
│   ├── agent/                # LangGraph 多 Agent 编排
│   │   ├── graph.py          # ★ 状态图 + HITL + Critic + 闲聊路由
│   │   ├── state.py          # ★ AgentState（含 v4.1 取证+处置字段）
│   │   ├── sse_adapter.py    # ★ SSE 流适配器（含 final_answer 补偿 + HITL 中断）
│   │   ├── prompts.py        # ★ 四个 Agent + Critic + 闲聊 提示词
│   │   ├── llm.py            # LLM 工厂（lru_cache）
│   │   └── nodes/            # Agent 节点实现
│   ├── tools/
│   │   ├── registry.py       # ★ 工具注册表（23 个工具）
│   │   ├── code_executor.py  # Python 沙箱（subprocess.run 白名单）
│   │   ├── file_io.py        # 文件读写
│   │   ├── log_query.py      # 日志查询
│   │   ├── cve_search.py     # CVE 检索
│   │   ├── rag_search.py     # 知识库检索
│   │   ├── recall_memory.py  # 记忆召回
│   │   ├── web_search.py     # 网络搜索
│   │   └── forensics/        # ★ v4.0/v4.1: 取证+处置工具包
│   │       ├── _utils.py             # 公共函数（PowerShell 封装，.replace 防注入）
│   │       ├── system_info.py        # 系统信息采集
│   │       ├── process_scanner.py    # 进程扫描（非管理员兼容）
│   │       ├── network_monitor.py    # 网络监控（netstat 回退）
│   │       ├── defender_checker.py   # Defender 检查
│   │       ├── login_auditor.py      # 登录审计（需管理员）
│   │       ├── startup_checker.py    # 启动项检查
│   │       ├── registry_scanner.py   # 注册表扫描
│   │       ├── file_integrity.py     # 文件完整性
│   │       ├── risk_engine.py        # 风险评分引擎
│   │       ├── test_forensics.py     # 端到端测试脚本
│   │       └── remediation/          # ★ v4.1: 处置工具
│   │           ├── kill_process.py       # 终止进程
│   │           ├── quarantine_file.py    # 隔离文件
│   │           ├── block_ip.py           # 封禁 IP
│   │           ├── remove_startup.py     # 清除启动项
│   │           ├── repair_registry.py    # 修复注册表
│   │           └── rollback.py           # 回滚操作
│   ├── memory/               # Redis 4 层长期记忆
│   ├── rag/                  # ChromaDB + Embedding + 灌库脚本
│   ├── model_router/         # 多模型路由 + CostTracker
│   ├── guardrails/           # 输入/输出护栏 + 审计日志
│   ├── mcp/                  # MCP Server + Client 节点
│   ├── a2a/                  # Agent-to-Agent 协议
│   ├── observability/        # LangSmith
│   ├── chat_api_v2.py        # v4 路由（+HITL resume +thread history +admin）
│   ├── server_v2.py          # v4 启动入口
│   └── config.yaml           # 统一配置 (+v4.1 remediation)
├── demo/chat/frontend/       # Next.js 14 前端（含 HITL 审批卡片 UI）
├── data/                     # Checkpoint DB + 备份文件
├── knowledge/                # 知识库种子数据（ATT&CK / CVE）
├── eval/                     # 评估系统 (10指标)
├── docs/
│   ├── DESIGN_V4_自主取证.md  # v4.0 自主取证设计文档
│   ├── RUNBOOK_V4_执行手册.md # v4.1 执行手册
│   ├── PROJECT_INTRO.md      # 项目介绍话术
│   ├── RESUME_BULLETS.md     # 简历素材
│   ├── INTERVIEW_QA.md       # 面试问答（智能体方向）
│   └── INTERVIEW_QA_BACKEND.md # 面试问答（后端方向）
├── docker-compose.yml        # Redis Stack + ChromaDB
├── requirements-v2.txt
├── start_all_v2.bat          # 一键启动
└── README.md
```

---

## 版本演进

| 版本 | 核心变化 |
|------|---------|
| v1.0 | 基础 CodeAct Agent + DeepSeek API |
| v2.0 | LangGraph 编排 + RAG + 长期记忆 + 多工具 |
| v3.0 | HITL + Critic + 多模型路由 + MCP + 安全护栏 |
| v4.0 | 8 个自主取证工具 + 风险评分引擎 + 端到端测试 |
| v4.1 | 6 个处置工具 + 前端审批 UI + 非管理员回退 + 处置回滚 |

---

## License

MIT
