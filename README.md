# DeepInvestigate v3.0

> **基于 LangGraph 的生产级多智能体安全调查系统**：融合 HITL、Critic 自审查、多模型路由、MCP 协议、安全护栏。

## 项目简介

DeepInvestigate 是一个 **CodeAct Multi-Agent** 系统：用户用自然语言提出问题，AI 自主拆解步骤、调用工具、迭代推理，最终给出结构化报告。

### v3.0 核心能力

- **多 Agent 编排**：基于 **LangGraph** 的 `Planner → Investigator → Reporter → Critic` 四 Agent 协作
- **HITL 人工审批**：危险工具调用前自动暂停，前端弹审批卡片
- **Checkpointing**：SQLite 持久化，支持会话恢复与时间旅行调试
- **Critic 自审查**：报告质量自动评分，不合格自动回退补充调查
- **多模型路由**：按节点分配模型，主模型不可用时自动 fallback，Token 成本追踪
- **MCP 协议**：工具封装为 MCP Server，跨项目/跨框架复用
- **安全护栏**：输入敏感词拦截 + 输出 PII 脱敏 + 审计日志
- **9 个工具**：通过 OpenAI Function Calling 标准协议调用
- **RAG 检索增强**：ChromaDB + BGE-M3 + MITRE ATT&CK / CVE 知识库
- **多层长期记忆**：基于 Redis Stack 的四层记忆 + Mem0
- **可观测 + 可评估**：LangSmith 全链路追踪 + 自研 10 指标评估体系

## 快速开始

### 系统要求

- Python 3.10+
- Node.js 16+
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

2. **停止所有服务**
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

## 使用方法

### 基本使用流程

1. **输入分析需求**：在聊天框中描述你想要完成的分析任务
2. **查看分析结果**：系统会自动处理数据并生成分析报告
3. **下载报告**：分析完成后，你可以下载生成的报告文件

---

## 架构（v3.0）

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
│   │ Planner │→ │ Investigator │→ │Reporter│→ │ Critic │     │
│   └─────────┘  └──────┬───────┘  └────────┘  └───┬────┘     │
│                  ┌────┴─────┐              ┌─────┴─────┐     │
│                  ▼          ▼              ▼           ▼     │
│            ┌──────────┐ ┌────────┐   ┌────────┐ ┌────────┐  │
│            │ToolNode  │ │Memory  │   │  HITL  │ │ Guard  │  │
│            │(9/MCP)   │ │4 layers│   │Approval│ │ rails  │  │
│            └──────────┘ └────────┘   └────────┘ └────────┘  │
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

### LangGraph 节点流程 (v3.0)

```
START → retrieve_memory → retrieve_knowledge → planner
                                                  ↓
                                            investigator ←──────────┐
                                              ↓                     │
                                        [human_approval] ← HITL     │
                                              ↓                     │
                                        tool_executor ──────────────┘
                                              ↓
                                            reporter
                                              ↓
                                            critic  ←── NEW
                                           ↙     ↘
                                      (pass)     (fail → investigator)
                                          ↓
                                    update_memory → END
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
| **工具协议** | OpenAI Function Calling · MCP (Model Context Protocol) |
| **安全** | HITL 人工审批 · Guardrails 输入/输出护栏 · PII 脱敏 · 审计日志 |
| **后端** | Python · FastAPI · Pydantic v2 · asyncio |
| **前端** | Next.js 14 · React 18 · TypeScript · TailwindCSS · shadcn/ui · Monaco Editor |
| **可观测** | LangSmith · CostTracker |
| **评估** | 自研指标体系（10 类） · 50+ 测试集 · 对抗样本 |
| **基础设施** | Docker Compose |

---

## 评估

```bash
# 跑全部 50+ 条评估
python -m eval.run_eval

# 只跑前 5 条快速冒烟
python -m eval.run_eval --limit 5

# 并发跑（注意 API 限流）
python -m eval.run_eval --concurrency 3
```

报告输出：`eval/reports/report_<timestamp>.json`，含：

- **Task Success Rate**：综合任务成功率
- **Keyword Coverage / Tool Call Accuracy / Avg Iterations / Avg Latency**
- **Hallucination Rate**：拒答/幻觉信号比例
- **Critic Score / Fallback Rate / Cost per Task** (v3.0 新增)
- **Success by Difficulty**：按 easy/medium/hard 分组的成功率

详细说明见 [`eval/README.md`](./eval/README.md)。

---

## 项目结构

```
deepinvestigate/
├── API/
│   ├── agent/              # ★ LangGraph Multi-Agent (v3: +HITL +Critic)
│   │   ├── nodes/          #   Planner / Investigator / Reporter / 记忆钩子
│   │   ├── graph.py        #   StateGraph 组装 (v3: +checkpointer +interrupt)
│   │   ├── sse_adapter.py  #   LangGraph 事件 → OpenAI SSE (v3: +HITL)
│   │   └── llm.py          #   (v3: +ModelRouter)
│   ├── tools/              # ★ 9 个工具（OpenAI Function Calling 协议）
│   ├── memory/             # ★ Redis 4 层记忆 + Mem0 适配
│   ├── rag/                # ★ ChromaDB + BGE-M3 + 灌库脚本
│   ├── model_router/       # ★ v3.0: 多模型路由 + CostTracker
│   ├── guardrails/         # ★ v3.0: 输入/输出护栏 + 审计日志
│   ├── mcp/                # ★ v3.0: MCP Server + Client 节点
│   ├── a2a/                # ★ v3.0: Agent-to-Agent 协议
│   ├── observability/      # ★ LangSmith
│   ├── chat_api_v2.py      # ★ v3 路由（+HITL resume +thread history +admin）
│   ├── server_v2.py        # ★ v3 启动入口
│   ├── chat_api_deepseek.py    # v1（保留）
│   └── config.yaml         # 统一配置 (v3: +models +mcp +hitl +guardrails)
├── demo/chat/frontend/     # Next.js 前端
├── knowledge/              # 知识库种子数据（ATT&CK / CVE）
├── eval/                   # ★ 评估系统 (v3: 10指标)
│   ├── dataset/            #   测试集 (50+)
│   ├── metrics.py
│   └── run_eval.py
├── docs/
│   ├── PRD_V3.md           # ★ v3.0 需求文档
│   ├── DESIGN_V3.md        # ★ v3.0 设计文档
│   └── DESIGN.md           # v2.0 设计文档
├── docker-compose.yml      # ★ Redis Stack + ChromaDB
├── requirements.txt
├── requirements-v2.txt     # ★ v2.0 新增依赖
├── start_all_v2.bat        # ★ v3 一键启动
└── start_all.bat           # v1 启动（保留）
```

