# DeepInvestigate v2.0 架构升级设计文档

> 目标：将现有的"自定义 OODA 循环 + DeepSeek API"单体智能体，升级为 **基于 LangGraph 的多智能体安全调查系统**，融合 RAG、长期记忆、可观测性、自动化评估等行业主流能力。

---

## 1. 设计目标

### 1.1 业务目标

- 让 Agent 具备 **跨会话学习能力**：能记住历史攻击模式、用户偏好、成功调查 SOP
- 让 Agent 具备 **领域知识增强能力**：调查时自动检索 MITRE ATT&CK、CVE、内部知识库
- 让 Agent 具备 **可观测、可评估能力**：每一步推理可追溯，效果可量化迭代

### 1.2 技术目标

| 维度 | v1.0 现状 | v2.0 目标 |
|---|---|---|
| Agent 框架 | 手写 `while` 循环 | LangGraph StateGraph |
| Agent 数量 | 单 Agent | 多 Agent（Planner / Investigator / Reporter） |
| 工具调用 | 自定义 `<Code>` 标签 | OpenAI Function Calling 标准 |
| 知识增强 | 无 | RAG（ChromaDB + BGE-M3 + MITRE ATT&CK） |
| 长期记忆 | 无 | 多层记忆（Redis Stack + Mem0） |
| 可观测性 | 仅日志 | LangSmith 全链路追踪 |
| 评估体系 | 无 | DeepEval 自动化评估 |

### 1.3 非目标

- 不改动前端 UI（保持 Next.js 现有界面）
- 不改动 DeepSeek API 接入方式（保持 OpenAI 兼容）
- 不重写文件服务、工作区管理等已稳定模块

---

## 2. 总体架构

### 2.1 系统分层

```
┌─────────────────────────────────────────────────────────────┐
│  前端 (Next.js + shadcn/ui)        端口 4000                │
└─────────────────────────────────────────────────────────────┘
                            │ SSE 流式
┌─────────────────────────────────────────────────────────────┐
│  API 层 (FastAPI)                  端口 8201                │
│  - /chat/completions (兼容 OpenAI)                          │
│  - /threads, /files, /admin                                 │
└─────────────────────────────────────────────────────────────┘
                            │
┌─────────────────────────────────────────────────────────────┐
│  Agent 编排层 (LangGraph)                                   │
│  ┌─────────┐  ┌──────────────┐  ┌────────┐                  │
│  │ Planner │→ │ Investigator │→ │Reporter│                  │
│  └─────────┘  └──────────────┘  └────────┘                  │
└─────────────────────────────────────────────────────────────┘
       │              │                  │
       ▼              ▼                  ▼
┌──────────┐  ┌─────────────────┐  ┌──────────────┐
│ 记忆服务 │  │   工具服务      │  │  RAG 服务    │
│ Redis +  │  │ Code Sandbox /  │  │ ChromaDB +   │
│ Mem0     │  │ Log Query / etc │  │ BGE-M3       │
└──────────┘  └─────────────────┘  └──────────────┘
                            │
┌─────────────────────────────────────────────────────────────┐
│  可观测层 (LangSmith) + 评估层 (DeepEval)                   │
└─────────────────────────────────────────────────────────────┘
                            │
┌─────────────────────────────────────────────────────────────┐
│  模型层 (DeepSeek API · OpenAI 兼容)                        │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 目录结构（升级后）

```
deepinvestigate/
├── API/
│   ├── main.py                  # FastAPI 入口（保留）
│   ├── chat_api_deepseek.py     # ← 改造：调用 agent 模块
│   ├── file_api.py              # 文件 API（保留）
│   ├── admin_api.py             # 管理 API（保留）
│   ├── config.yaml              # 配置（扩展）
│   │
│   ├── agent/                   # 【新增】Agent 编排
│   │   ├── __init__.py
│   │   ├── graph.py             # LangGraph StateGraph 定义
│   │   ├── state.py             # AgentState 状态对象
│   │   ├── nodes/
│   │   │   ├── planner.py       # 规划 Agent
│   │   │   ├── investigator.py  # 调查 Agent
│   │   │   └── reporter.py      # 报告 Agent
│   │   └── prompts.py           # 各 Agent 的 Prompt
│   │
│   ├── tools/                   # 【新增】工具集
│   │   ├── __init__.py
│   │   ├── code_executor.py     # 代码沙箱（迁移 utils.py 的 execute_code_safe）
│   │   ├── log_query.py         # 日志查询
│   │   ├── cve_search.py        # CVE 检索
│   │   ├── rag_search.py        # RAG 知识库查询
│   │   ├── memory_recall.py     # 记忆召回
│   │   ├── file_io.py           # 文件读写
│   │   ├── web_search.py        # 网络搜索（可选）
│   │   └── registry.py          # 工具注册表
│   │
│   ├── memory/                  # 【新增】长期记忆
│   │   ├── __init__.py
│   │   ├── redis_client.py      # Redis Stack 连接
│   │   ├── working_memory.py    # 工作记忆（TTL）
│   │   ├── episodic_memory.py   # 情景记忆（向量）
│   │   ├── semantic_memory.py   # 语义记忆（JSON）
│   │   ├── procedural_memory.py # 程序记忆（SOP）
│   │   └── mem0_adapter.py      # Mem0 集成
│   │
│   ├── rag/                     # 【新增】RAG
│   │   ├── __init__.py
│   │   ├── chroma_client.py     # ChromaDB 连接
│   │   ├── embedder.py          # BGE-M3 嵌入
│   │   ├── ingest.py            # 知识库导入（ATT&CK / CVE）
│   │   └── retriever.py         # 检索接口
│   │
│   ├── observability/           # 【新增】可观测性
│   │   ├── __init__.py
│   │   └── langsmith_setup.py
│   │
│   └── utils.py                 # 保留（代码沙箱等迁移到 tools）
│
├── eval/                        # 【新增】评估
│   ├── dataset/
│   │   └── attack_logs_50.jsonl # 测试集
│   ├── metrics.py               # 评估指标
│   ├── run_eval.py              # 评估入口
│   └── reports/                 # 评估结果
│
├── knowledge/                   # 【新增】知识库源数据
│   ├── mitre_attack/
│   └── cve/
│
├── docker-compose.yml           # 【新增】启动 Redis Stack + ChromaDB
├── docs/
│   └── DESIGN.md                # 本文档
├── demo/                        # 前端（保留）
└── requirements.txt             # 【更新】新增依赖
```

---

## 3. 核心模块设计

### 3.1 Agent 编排（LangGraph）

#### 3.1.1 状态对象

```python
# API/agent/state.py
from typing import TypedDict, List, Dict, Annotated, Optional
from langgraph.graph.message import add_messages

class AgentState(TypedDict):
    # 输入
    user_query: str
    thread_id: str
    user_id: str
    workspace_dir: str

    # 消息历史（LangGraph 自动合并）
    messages: Annotated[list, add_messages]

    # 任务规划
    plan: Optional[List[str]]
    current_step: int

    # 检索增强
    retrieved_knowledge: List[Dict]
    recalled_memories: List[Dict]

    # 工具执行
    tool_calls: List[Dict]
    tool_results: List[Dict]

    # 输出
    final_answer: Optional[str]
    generated_files: List[str]

    # 控制流
    next_agent: Optional[str]  # "investigator" | "reporter" | "END"
    iteration_count: int
    max_iterations: int
```

#### 3.1.2 图结构

```python
# API/agent/graph.py（伪代码）
from langgraph.graph import StateGraph, END

def build_agent_graph():
    g = StateGraph(AgentState)

    # 节点
    g.add_node("retrieve_memory", retrieve_memory_node)   # 召回记忆
    g.add_node("retrieve_knowledge", rag_retrieval_node)  # RAG 检索
    g.add_node("planner", planner_node)                   # 任务规划
    g.add_node("investigator", investigator_node)         # 调查执行
    g.add_node("tool_executor", ToolNode(TOOLS))          # 工具执行
    g.add_node("reporter", reporter_node)                 # 报告生成
    g.add_node("update_memory", update_memory_node)       # 写入记忆

    # 边
    g.set_entry_point("retrieve_memory")
    g.add_edge("retrieve_memory", "retrieve_knowledge")
    g.add_edge("retrieve_knowledge", "planner")
    g.add_edge("planner", "investigator")

    # 调查 Agent 的条件路由
    g.add_conditional_edges(
        "investigator",
        route_after_investigator,
        {
            "use_tool": "tool_executor",
            "to_reporter": "reporter",
            "continue": "investigator",
        }
    )
    g.add_edge("tool_executor", "investigator")
    g.add_edge("reporter", "update_memory")
    g.add_edge("update_memory", END)

    return g.compile(checkpointer=redis_checkpointer)
```

#### 3.1.3 三个 Agent 的职责

| Agent | 输入 | 输出 | 模型温度 |
|---|---|---|---|
| **Planner** | 用户问题 + 记忆 + 知识 | 拆解后的步骤列表 | 0.3 |
| **Investigator** | 步骤 + 工具结果 | 工具调用 / 中间结论 | 0.4 |
| **Reporter** | 全部调查记录 | 结构化最终报告 | 0.5 |

---

### 3.2 工具系统（Function Calling）

#### 3.2.1 工具列表（8 类）

| 工具名 | 功能 | 输入 | 输出 |
|---|---|---|---|
| `run_python` | Python 代码沙箱 | code: str | stdout/stderr/files |
| `read_file` | 读取 workspace 文件 | path: str | content |
| `write_file` | 写入文件 | path, content | success |
| `query_logs` | 日志结构化查询 | query, time_range | rows |
| `search_cve` | CVE 信息查询 | cve_id / keyword | cve_detail |
| `rag_search` | 知识库检索 | query, top_k | docs |
| `recall_memory` | 长期记忆召回 | query, mem_type | memories |
| `web_search` | 网络搜索（可选） | query | results |

#### 3.2.2 工具协议

全部采用 **OpenAI Function Calling Tool Schema**：

```python
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "run_python",
            "description": "在沙箱中执行 Python 代码并返回输出",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "可执行的 Python 代码"}
                },
                "required": ["code"]
            }
        }
    },
    # ...
]
```

#### 3.2.3 代码沙箱（强化版）

在现有 `execute_code_safe` 基础上增加：

- **资源限制**：CPU 时间 / 内存上限（用 `resource` 模块或 Docker）
- **网络隔离**：默认禁网，白名单放行
- **文件系统隔离**：限制只能读写 workspace 目录
- **超时控制**：保持现有 30s 超时
- **危险操作拦截**：禁用 `os.system`, `subprocess` 调用主机

---

### 3.3 RAG 子系统

#### 3.3.1 知识源

| 来源 | 内容 | 更新频率 |
|---|---|---|
| **MITRE ATT&CK** | 战术、技术、过程 (TTP) | 季度 |
| **CVE 数据库** | 漏洞详情 | 每周 |
| **内部知识库** | 自定义文档 / SOP | 按需 |

#### 3.3.2 流程

```
[文档] → 分块 (chunk_size=512, overlap=64)
      → BGE-M3 Embedding (1024 维)
      → ChromaDB (Collection: knowledge_base)
      → 查询时 top_k=5 + 重排
```

#### 3.3.3 检索接口

```python
class Retriever:
    def search(self, query: str, top_k: int = 5,
               filter: Optional[dict] = None) -> List[Document]:
        ...
```

---

### 3.4 长期记忆子系统（Redis Stack）

#### 3.4.1 记忆分层

| 层级 | 存储方式 | Key 模式 | TTL |
|---|---|---|---|
| **工作记忆** | Redis String / Hash | `wm:{thread_id}` | 30 min |
| **情景记忆** | RediSearch HNSW + Hash | `em:{user_id}:{uuid}` | 永久 |
| **语义记忆** | RedisJSON | `sm:{user_id}` | 永久 |
| **程序记忆** | Redis Hash | `pm:{pattern_id}` | 永久 |

#### 3.4.2 向量索引（情景记忆）

```python
# 索引定义
FT.CREATE memory_idx ON HASH PREFIX 1 "em:" SCHEMA
    content   TEXT
    user_id   TAG
    timestamp NUMERIC SORTABLE
    tags      TAG SEPARATOR ","
    embedding VECTOR HNSW 6 TYPE FLOAT32 DIM 1024 DISTANCE_METRIC COSINE
```

#### 3.4.3 记忆生命周期

| 阶段 | 触发点 | 操作 |
|---|---|---|
| **写入** | Agent 完成调查后 | Mem0 抽取 → 去重 → 存 Redis |
| **召回** | Agent 启动时 | 向量检索 top 5 |
| **更新** | 用户纠正时 | 标记冲突 → 合并/覆盖 |
| **遗忘** | 工作记忆超 TTL | 自动过期 |

#### 3.4.4 Mem0 集成

```python
from mem0 import Memory

config = {
    "vector_store": {
        "provider": "redis",
        "config": {"host": "localhost", "port": 6379}
    },
    "embedder": {"provider": "huggingface", "config": {"model": "BAAI/bge-m3"}},
    "llm": {"provider": "deepseek", "config": {...}}
}

mem = Memory.from_config(config)
mem.add(messages, user_id="user_123")
results = mem.search("SSH 暴力破解", user_id="user_123")
```

---

### 3.5 可观测性（LangSmith）

#### 3.5.1 追踪点

- 每个 LangGraph 节点的输入输出
- 每次 LLM 调用的 token 数、延迟、成本
- 每次工具调用的参数、结果、异常
- 每次 RAG 检索的查询、命中结果
- 每次记忆召回的查询、命中

#### 3.5.2 配置

```python
import os
os.environ["LANGCHAIN_TRACING_V2"] = "true"
os.environ["LANGCHAIN_PROJECT"] = "DeepInvestigate-Prod"
os.environ["LANGCHAIN_API_KEY"] = "..."
```

---

### 3.6 评估子系统（DeepEval）

#### 3.6.1 测试集格式

```jsonl
{"task_id": "001", "input": "分析这份 SSH 日志找出异常", "expected_findings": ["暴力破解", "异常 IP"], "log_file": "ssh_001.log"}
```

#### 3.6.2 评估指标

| 指标 | 说明 |
|---|---|
| **Task Success Rate** | 是否完成用户目标 |
| **Tool Call Accuracy** | 工具调用是否正确 |
| **Hallucination Rate** | 是否凭空捏造结论 |
| **Avg Iterations** | 平均推理轮数 |
| **Avg Latency** | 平均完成时间 |
| **Avg Cost** | 平均 token 成本 |

#### 3.6.3 评估流程

```
[测试集] → 批量跑 Agent → 收集结果
        → DeepEval 评分 (G-Eval / 自定义 metric)
        → 生成对比报告（vs baseline）
```

---

## 4. 关键流程

### 4.1 一次完整调查的端到端流程

```
1. 用户输入："分析这份日志，是否存在 SSH 暴力破解"

2. retrieve_memory 节点
   - 查工作记忆：当前会话上下文
   - 查情景记忆：历史是否调查过类似问题 → 命中 2 条
   - 查语义记忆：用户偏好 → "高级分析师，关注根本原因"

3. retrieve_knowledge 节点
   - RAG 检索 MITRE ATT&CK：T1110 Brute Force → 5 条相关 TTP

4. planner 节点（LLM）
   - 输出步骤：
     [1] 加载日志文件并统计登录尝试
     [2] 识别失败次数 Top IP
     [3] 关联时间窗口判断暴力破解模式
     [4] 检查这些 IP 的威胁情报
     [5] 给出结论与处置建议

5. investigator 节点循环
   ├─ 步骤 1：调用 run_python 加载日志
   ├─ 步骤 2：调用 run_python 统计
   ├─ 步骤 3：调用 run_python 时间序列分析
   ├─ 步骤 4：调用 search_cve / rag_search 查威胁情报
   └─ 累积中间结论

6. reporter 节点
   - 输出结构化报告（执行摘要 / 发现 / 风险评级 / 建议）

7. update_memory 节点
   - 写情景记忆：本次调查结果
   - 更新语义记忆：用户的关注点
   - 沉淀程序记忆：成功 SOP

8. LangSmith 全程追踪 + 流式 SSE 输出到前端
```

### 4.2 流式输出策略

LangGraph 原生支持 `.astream()`，事件类型：

- `on_chain_start` → 通知前端"进入 Planner 节点"
- `on_llm_new_token` → 流式输出 Token
- `on_tool_start` / `on_tool_end` → 通知前端"正在执行 XX 工具"
- `on_chain_end` → 节点完成

转换为兼容 OpenAI 的 SSE chunk 返回。

---

## 5. 数据模型

### 5.1 Redis Key 命名规范

```
wm:{thread_id}                  String   工作记忆 (JSON)
em:{user_id}:{uuid}             Hash     情景记忆条目
em_idx                          Index    情景记忆向量索引
sm:{user_id}                    JSON     语义记忆 / 用户画像
pm:{pattern_id}                 Hash     程序记忆 / SOP
session:{thread_id}             Hash     会话元数据
ckpt:{thread_id}:{ts}           String   LangGraph checkpoint
```

### 5.2 情景记忆条目结构

```json
{
  "id": "uuid",
  "user_id": "u_001",
  "content": "用户调查了 SSH 暴力破解，确认来源 IP 1.2.3.4 来自境外，已封禁",
  "embedding": [0.1, 0.2, ...],
  "tags": "ssh,brute_force,blocked",
  "timestamp": 1716528000,
  "source_thread_id": "session_xxx",
  "confidence": 0.95
}
```

---

## 6. 配置与依赖

### 6.1 新增依赖（requirements.txt）

```
# Agent 框架
langgraph>=0.2.0
langchain>=0.3.0
langchain-openai>=0.2.0

# RAG
chromadb>=0.5.0
sentence-transformers>=3.0.0    # BGE-M3

# 记忆
redis>=5.0.0
mem0ai>=0.1.0

# 可观测
langsmith>=0.1.0

# 评估
deepeval>=1.0.0
```

### 6.2 配置文件扩展（config.yaml）

```yaml
api:
  base: "https://api.deepseek.com/v1"
  model_path: "deepseek-chat"
  api_key: "..."

redis:
  host: "localhost"
  port: 6379
  db: 0

chroma:
  host: "localhost"
  port: 8000
  collection: "knowledge_base"

embedder:
  model: "BAAI/bge-m3"
  device: "cpu"

langsmith:
  enabled: true
  project: "DeepInvestigate-Prod"
  api_key: "..."

agent:
  max_iterations: 15
  recursion_limit: 25
  default_temperature: 0.4
```

### 6.3 Docker Compose

```yaml
version: "3.8"
services:
  redis:
    image: redis/redis-stack:latest
    ports: ["6379:6379", "8001:8001"]
    volumes: ["./data/redis:/data"]

  chroma:
    image: chromadb/chroma:latest
    ports: ["8000:8000"]
    volumes: ["./data/chroma:/chroma/chroma"]
```

---

## 7. API 兼容性

### 7.1 对外接口保持不变

```
POST /chat/completions   （OpenAI 兼容）
POST /threads
POST /threads/{tid}/messages
GET  /files/{fid}/content
...
```

### 7.2 内部改动

- `chat_api_deepseek.py` 中的 `generate_stream_with_execution()` 函数 → 替换为调用 `agent.graph.astream()`
- 流式事件 → 转换为 OpenAI SSE chunk 返回
- 前端**无需改动**

---

## 8. 实施计划

按依赖顺序，分 5 个 Sprint：

### Sprint 1：基础设施（1 天）
- [ ] Docker Compose 起 Redis Stack + ChromaDB
- [ ] requirements.txt 更新并安装
- [ ] config.yaml 扩展
- [ ] `redis_client.py` / `chroma_client.py` / `embedder.py` 三个连接模块

### Sprint 2：工具系统（1-2 天）
- [ ] `tools/registry.py` 工具注册表
- [ ] 迁移 `execute_code_safe` → `tools/code_executor.py`（加强化）
- [ ] 实现其他 7 个工具
- [ ] 单元测试

### Sprint 3：LangGraph 主流程（2-3 天）
- [ ] `agent/state.py` 状态对象
- [ ] `agent/nodes/planner.py` / `investigator.py` / `reporter.py`
- [ ] `agent/graph.py` 组装 StateGraph
- [ ] 替换 `chat_api_deepseek.py` 的核心循环
- [ ] 端到端跑通最小 Demo

### Sprint 4：记忆 + RAG（2 天）
- [ ] `memory/` 四类记忆模块 + Mem0 集成
- [ ] `rag/ingest.py` 导入 MITRE ATT&CK
- [ ] 在 LangGraph 中接入 `retrieve_memory` / `retrieve_knowledge` / `update_memory` 节点

### Sprint 5：可观测 + 评估（2 天）
- [ ] LangSmith 接入
- [ ] 准备评估测试集（50 条）
- [ ] `eval/run_eval.py` 评估脚本
- [ ] 跑 baseline + v2.0 对比报告

**总工时**：约 8-10 天

---

## 9. 风险与缓解

| 风险 | 概率 | 影响 | 缓解措施 |
|---|---|---|---|
| LangGraph 流式输出与现有 SSE 协议不兼容 | 中 | 高 | 写一层适配器，提前调研 `astream_events` |
| Redis HNSW 向量检索精度不够 | 低 | 中 | 提供 ChromaDB 作为备选 |
| DeepSeek API 不完全支持 Function Calling | 中 | 高 | 已验证支持，否则回退到 JSON 模式 |
| BGE-M3 本地推理慢 | 中 | 中 | 用 ONNX 加速 / 改用 API 嵌入 |
| 多 Agent 导致 token 成本上升 | 高 | 中 | Planner 用小模型 / 加缓存 |
| 长期记忆出现脏数据/冲突 | 中 | 中 | Mem0 自带去重 + 加冲突检测节点 |

---

## 10. 验收标准

### 10.1 功能验收

- [ ] 用户在前端发起一次调查，端到端流程跑通
- [ ] LangSmith 后台能看到完整 trace
- [ ] Redis 中能看到 4 类记忆都有数据写入
- [ ] 第二次类似调查能命中历史记忆并复用
- [ ] RAG 能正确检索 ATT&CK 知识

### 10.2 性能验收

- [ ] 平均响应时间 ≤ 现有版本 +30%
- [ ] 重复任务通过记忆复用，迭代轮数下降 ≥ 50%

### 10.3 质量验收

- [ ] 在 50 条测试集上，任务成功率 ≥ 80%
- [ ] 工具调用准确率 ≥ 90%
- [ ] 幻觉率 ≤ 10%

---

## 11. 附录

### 11.1 关键术语

- **CodeAct Agent**：Agent 通过编写并执行代码完成任务的范式
- **ReAct**：Reasoning + Acting，思考-行动交替的推理模式
- **Function Calling**：LLM 输出结构化函数调用请求的能力
- **RAG**：Retrieval-Augmented Generation 检索增强生成
- **HNSW**：Hierarchical Navigable Small World，向量检索算法
- **TTP**：Tactics, Techniques, Procedures（MITRE 术语）

### 11.2 参考资料

- LangGraph 官方文档：https://langchain-ai.github.io/langgraph/
- Redis Stack 向量搜索：https://redis.io/docs/latest/develop/interact/search-and-query/
- Mem0 文档：https://docs.mem0.ai/
- MITRE ATT&CK：https://attack.mitre.org/
- DeepEval：https://docs.confident-ai.com/

---

**文档版本**：v1.0
**作者**：DeepInvestigate Team
**最后更新**：2026-05-24
**状态**：✅ 待评审 → 评审通过后进入实施
