# DeepInvestigate v4.0

> **基于 LangGraph 的自主取证多智能体安全调查系统**：感知 -> 分析 -> 行动完整闭环，自己采集证据、自己分析研判、自己生成报告。

## 项目简介

DeepInvestigate 是一个**真正自主的安全调查智能体**——不是等用户喂数据，而是自己调用取证工具采集主机信息，再通过四 Agent 协作完成分析研判，最终给出结构化调查报告。

**与聊天助手的本质区别：** 你说"帮我查这台机器有没有被入侵"，它自己动手查，而不是说"请把日志发给我"。

### v4.0 核心能力

- **自主取证引擎 (NEW)**：8 个主机取证工具，自主采集进程、网络、登录、启动项、注册表、文件、Defender 日志等
- **多 Agent 编排**：基于 **LangGraph** 的 `Planner -> Investigator -> Reporter -> Critic` 四 Agent 协作
- **风险评分引擎 (NEW)**：0-100 分量化评估，关联加权算法，MITRE ATT&CK 技战术映射
- **HITL 人工审批**：危险工具（Level 0/1/2）调用前自动暂停，前端弹审批卡片
- **Checkpointing**：SQLite 持久化，支持会话恢复与时间旅行调试
- **Critic 自审查**：报告质量自动评分，新增证据充分性维度，不合格自动回退补充调查
- **多模型路由**：按节点分配模型，主模型不可用时自动 fallback，Token 成本追踪
- **MCP 协议**：工具封装为 MCP Server，跨项目/跨框架复用
- **安全护栏**：输入敏感词拦截 + 输出 PII 脱敏 + 审计日志
- **17 个工具**：9 个分析工具 + 8 个取证工具，通过 OpenAI Function Calling 标准协议调用
- **RAG 检索增强**：ChromaDB + BGE-M3 + MITRE ATT&CK / CVE 知识库
- **多层长期记忆**：基于 Redis Stack 的四层记忆 + Mem0
- **可观测 + 可评估**：LangSmith 全链路追踪 + 自研 10 指标评估体系 + v4.0 端到端测试脚本

---

## 快速开始

### 系统要求

- Python 3.10+
- Node.js 16+
- Windows 10/11（取证工具依赖 PowerShell）
- 推荐使用 conda 环境管理工具

### 安装步骤

1. **启动基础设施（v2.0 必需）**
   ```bash
   # Redis Stack + ChromaDB
   docker compose up -d
   ```

2. **安装 Python 依赖**
   ```bash
   conda create -n DeepInvestigate python=3.12 -y
   conda activate DeepInvestigate
   pip install -r requirements.txt
   pip install -r requirements-v2.txt    # v2.0 新增依赖
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
   - 编辑 `API/config.yaml` 文件，填写你的 DeepSeek API 密钥
   - 可选：填入 `langsmith.api_key` 启用全链路追踪

### 运行服务

项目提供了便捷的启动和停止脚本，支持 Windows 和 Linux 系统：

#### Windows 系统（v2.0 推荐）

1. **启动所有服务（v2.0 LangGraph 版本）**
   ```bash
   .\start_all_v2.bat
   ```
   该脚本会依次：
   - 起 Redis Stack + ChromaDB（docker compose）
   - 启动 v2 后端（`API/server_v2.py`）
   - 启动前端（Next.js）

2. **启动 v1 版本（兼容回退）**
   ```bash
   .\start_all.bat
   ```

3. **停止所有服务**
   ```bash
   # 双击运行或在命令行执行
   .\stop_all.bat
   ```

#### Linux 系统

1. **设置执行权限**
   ```bash
   chmod +x start_all.sh stop_all.sh
   ```

2. **启动所有服务**
   ```bash
   ./start_all.sh
   ```

3. **停止所有服务**
   ```bash
   ./stop_all.sh
   ```

### 访问服务

服务启动后，你可以通过以下地址访问：

- **前端界面**：http://localhost:4000
- **后端 API**：http://localhost:8201
- **文件服务**：http://localhost:8101
- **RedisInsight**：http://localhost:8001 （记忆数据可视化）

---

## v4.0 端到端测试

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

### 主机安全调查（v4.0 核心场景）

1. **输入调查指令**：在聊天框中输入"帮我检查这台主机有没有被入侵"
2. **系统自主取证**：Planner 制定计划，Investigator 自主调用 8 个取证工具采集证据
3. **智能分析研判**：结合 MITRE ATT&CK 知识库，对采集数据进行威胁研判
4. **生成调查报告**：包含 IoC 指标、风险评分、MITRE 技战术映射、处置建议

### 其他分析场景

1. **日志分析**：上传日志文件，系统自动结构化查询和分析
2. **漏洞评估**：查询 CVE 漏洞信息，评估主机补丁状态
3. **知识问答**：利用内置 MITRE ATT&CK / CVE 知识库回答问题
4. **下载报告**：分析完成后，可以下载生成的报告文件

---

## 架构（v4.0）

```
┌──────────────────────────────────────────────────────────────┐
│        前端 (Next.js + shadcn/ui)           :4000            │
│        + HITL 审批卡片 + 用量面板                             │
└──────────────────────────────────────────────────────────────┘
                       │ SSE 流式 + HITL Command
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
│                  ┌────┴─────────────┐         ┌──┴──────┐    │
│                  ▼                  ▼         ▼         ▼    │
│            ┌──────────┐    ┌────────────┐ ┌──────┐ ┌──────┐  │
│            │17 Tools  │    │  Forensics  │ │ HITL │ │Guard │  │
│            │(9+8 v4.0)│    │  (8 Tools)  │ │ L0-2 │ │rails │  │
│            └──────────┘    └────────────┘ └──────┘ └──────┘  │
│            ┌──────────┐    ┌────────────┐                    │
│            │  Memory  │    │Risk Engine │                    │
│            │ 4 layers │    │ (0-100分)  │                    │
│            └──────────┘    └────────────┘                    │
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

### LangGraph 节点流程 (v4.0)

```
START -> retrieve_memory -> retrieve_knowledge -> planner
                                                    ↓
                                              investigator <----------+
                                                ↓                     |
                                          [自主取证阶段]               |
                                          collect_system_info         |
                                          scan_processes              |
                                          check_network               |
                                          check_defender_logs         |
                                          ...                         |
                                                ↓                     |
                                          [分析阶段]                  |
                                          run_python 分析             |
                                          MITRE ATT&CK 映射           |
                                          search_cve                  |
                                                ↓                     |
                                          [human_approval] <- HITL    |
                                                ↓                     |
                                          tool_executor --------------+
                                                ↓
                                              reporter
                                                ↓
                                              critic  <-- v4.0增强
                                             /       \
                                        (pass)     (fail -> investigator)
                                            ↓
                                      update_memory -> END
```

---

## 技术栈

| 类别 | 技术 |
|---|---|
| **Agent 框架** | LangGraph · LangChain · Checkpointer (SQLite) |
| **模型** | DeepSeek · OpenAI (多模型路由 + fallback) |
| **Embedding** | BGE-M3 (HuggingFace) / OpenAI Embeddings |
| **向量库** | ChromaDB（知识库） + RediSearch HNSW（记忆） |
| **长期记忆** | Redis Stack 4 层（工作 / 情景 / 语义 / 程序） + Mem0 |
| **后端** | FastAPI · Uvicorn · SSE 流式 · async/await |
| **前端** | Next.js · React · shadcn/ui · Tailwind CSS |
| **HITL** | LangGraph interrupt() + 自定义审批 UI |
| **安全** | 输入护栏 · 输出 PII 脱敏 · 工具风险等级 · 命令白名单 |
| **v4.0 取证** | PowerShell · WMIC · wevtutil · schtasks · Get-WinEvent · 进程签名验证 |
| **可观测性** | LangSmith · 结构化日志 · Token 成本追踪 |
| **评估** | 自研 10 指标评估体系 · 50+ 测试集 · 端到端测试脚本 |
| **协议** | OpenAI Function Calling · MCP · A2A (Agent-to-Agent) |

---

## 取证工具清单 (v4.0)

| 工具 | 风险等级 | 功能 |
|------|---------|------|
| `collect_system_info` | Level 0 | 采集 OS 版本、用户、补丁、杀软、防火墙状态 |
| `scan_processes` | Level 1 | 枚举所有进程 + 可疑分析（签名验证、路径检查、命令行检测） |
| `check_network` | Level 1 | 检查网络连接 + 可疑外联识别（C2 通信检测） |
| `check_defender_logs` | Level 1 | 查询 Defender 告警历史和当前状态 |
| `check_startup` | Level 1 | 检查启动项、计划任务、服务持久化 |
| `check_file_integrity` | Level 1 | 文件完整性检查（临时目录、ADS、关键 DLL 哈希） |
| `audit_logins` | Level 2 | 登录审计（暴力破解、RDP 异常、非工作时间登录） |
| `scan_registry` | Level 2 | 注册表可疑项扫描（持久化、DLL 注入、UAC 绕过） |

---

## 项目结构

```
deepinvestigate_3.0/
├── API/
│   ├── agent/                # LangGraph 多 Agent 编排
│   │   ├── graph.py          # ★ 状态图 + HITL + Critic
│   │   ├── state.py          # ★ AgentState（含 v4.0 取证字段）
│   │   ├── prompts.py        # ★ 四个 Agent 提示词（v4.0 增强）
│   │   ├── llm.py            # LLM 工厂
│   │   └── nodes/            # Agent 节点实现
│   ├── tools/
│   │   ├── registry.py       # ★ 工具注册表（17 个工具）
│   │   ├── code_executor.py  # Python 沙箱执行
│   │   ├── file_io.py        # 文件读写
│   │   ├── log_query.py      # 日志查询
│   │   ├── cve_search.py     # CVE 检索
│   │   ├── rag_search.py     # 知识库检索
│   │   ├── recall_memory.py  # 记忆召回
│   │   ├── web_search.py     # 网络搜索
│   │   └── forensics/        # ★ v4.0: 自主取证工具包
│   │       ├── _utils.py             # 公共函数（PowerShell 封装）
│   │       ├── system_info.py        # 系统信息采集
│   │       ├── process_scanner.py    # 进程扫描
│   │       ├── network_monitor.py    # 网络监控
│   │       ├── defender_checker.py   # Defender 检查
│   │       ├── login_auditor.py      # 登录审计
│   │       ├── startup_checker.py    # 启动项检查
│   │       ├── registry_scanner.py   # 注册表扫描
│   │       ├── file_integrity.py     # 文件完整性
│   │       ├── risk_engine.py        # 风险评分引擎
│   │       └── test_forensics.py     # 端到端测试脚本
│   ├── memory/               # Redis 4 层长期记忆
│   ├── rag/                  # ChromaDB + BGE-M3 + 灌库脚本
│   ├── model_router/         # 多模型路由 + CostTracker
│   ├── guardrails/           # 输入/输出护栏 + 审计日志
│   ├── mcp/                  # MCP Server + Client 节点
│   ├── a2a/                  # Agent-to-Agent 协议
│   ├── observability/        # LangSmith
│   ├── chat_api_v2.py        # v3 路由（+HITL resume +thread history +admin）
│   ├── server_v2.py          # v3 启动入口
│   ├── chat_api_deepseek.py  # v1（保留）
│   └── config.yaml           # 统一配置 (+v4.0 forensics)
├── demo/chat/frontend/       # Next.js 前端
├── knowledge/                # 知识库种子数据（ATT&CK / CVE）
├── eval/                     # 评估系统 (10指标)
│   ├── dataset/              #   测试集 (50+)
│   ├── metrics.py
│   └── run_eval.py
├── docs/
│   ├── PRD_V3.md             # v3.0 需求文档
│   ├── DESIGN_V3.md          # v3.0 设计文档
│   ├── DESIGN_V4_自主取证.md  # ★ v4.0 自主取证设计文档
│   └── DESIGN.md             # v2.0 设计文档
├── docker-compose.yml        # Redis Stack + ChromaDB
├── requirements.txt
├── requirements-v2.txt       # v2.0 新增依赖
├── start_all_v2.bat          # v3 一键启动
└── start_all.bat             # v1 启动（保留）
```

---

## 设计文档

- [v4.0 自主取证设计文档](docs/DESIGN_V4_自主取证.md) — 感知层工具集、Agent 编排、风险评分引擎、实施计划
- [v3.0 产品需求文档](docs/PRD_V3.md) — HITL、Critic、多模型路由、安全护栏
- [v3.0 架构设计文档](docs/DESIGN_V3.md) — 系统架构、数据流、部署方案
- [v2.0 设计文档](docs/DESIGN.md) — 基础架构

---

## 版本演进

| 版本 | 核心变化 |
|------|---------|
| v1.0 | 基础 CodeAct Agent + DeepSeek API |
| v2.0 | LangGraph 编排 + RAG + 长期记忆 + 多工具 |
| v3.0 | HITL + Critic + 多模型路由 + MCP + 安全护栏 |
| v4.0 | 自主取证引擎 + 风险评分引擎 + 8 个取证工具 + 端到端测试 |

---

## License

MIT