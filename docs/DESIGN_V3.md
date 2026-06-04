# DeepInvestigate v3.0 架构升级设计文档

> 目标：在 v2.0 基础上补齐 Agent 深度、工程可靠性与前沿性短板，从"Demo 级全栈项目"升级为"生产级 Agent 系统"。
>
> 前置文档：[PRD_V3.md](./PRD_V3.md)

---

## 1. 设计目标

### 1.1 业务目标

- 让工具可跨项目复用（MCP 标准协议）
- 让危险操作有人工兜底（HITL 审批）
- 让会话可断点续跑与回溯调试（Checkpointing）
- 让报告质量有自检闭环（Critic Agent）
- 让模型调用有路由、降级与成本感知
- 让输入输出有安全护栏与审计
- 让评估体系有足够说服力（50+ 条 / 对抗样本）
- 让 Agent 间有显式通信协议（A2A）

### 1.2 技术目标

| 维度 | v2.0 现状 | v3.0 目标 |
|---|---|---|
| 工具复用 | 仅本项目可用 | MCP Server，跨项目/跨框架复用 |
| 安全审批 | 无 | HITL 三级审批 + 前端审批卡片 |
| 会话持久化 | 无 | SQLite Checkpointer + 时间旅行 |
| 质量控制 | 无 | Critic Agent 自审查 + 条件回退 |
| 模型管理 | 单一 DeepSeek | 多模型路由 + fallback + 成本追踪 |
| 安全护栏 | 仅代码沙箱 | 输入/输出护栏 + PII 脱敏 + 审计 |
| 评估规模 | 15 条 / 6 指标 | 50+ 条 / 10 指标 / 对抗样本 |
| Agent 通信 | 隐式（共享状态） | A2A 显式协议 + 并行调查 |

### 1.3 非目标

- 不改动前端核心交互流程（审批卡片为唯一新增 UI）
- 不引入新的基础设施依赖（继续 Docker Compose）
- 不重写 v2.0 已稳定的记忆、RAG、工具模块（仅扩展）
- 不改变对外 API 协议（保持 OpenAI Chat Completions 兼容）

---

## 2. 总体架构

### 2.1 系统分层（v3.0）

```
┌──────────────────────────────────────────────────────────────────┐
│  前端 (Next.js + shadcn/ui)             端口 4000                │
│  + 审批卡片组件 (HITL)                                           │
│  + 用量面板 (Admin)                                              │
└──────────────────────────────────────────────────────────────────┘
                            │ SSE 流式 + HITL Command
┌──────────────────────────────────────────────────────────────────┐
│  API 层 (FastAPI)                       端口 8201                │
│  - POST /chat/completions     (兼容 OpenAI + session_id 恢复)    │
│  - POST /chat/resume          (HITL 审批恢复)                    │
│  - GET  /threads/{id}/history (时间旅行)                         │
│  - GET  /admin/usage          (成本追踪)                         │
│  - GET  /admin/audit          (护栏审计)                         │
└──────────────────────────────────────────────────────────────────┘
                            │
┌──────────────────────────────────────────────────────────────────┐
│  Agent 编排层 (LangGraph + Checkpointer)                         │
│                                                                  │
│  retrieve_memory → retrieve_knowledge → planner                  │
│                                              ↓                   │
│                                        investigator ←────────┐   │
│                                          ↓                   │   │
│                                   [human_approval] ← HITL    │   │
│                                          ↓                   │   │
│                                     tool_executor ──────────┘   │
│                                     │  mcp_tool_executor         │
│                                          ↓                       │
│                                        reporter                  │
│                                          ↓                       │
│                                        critic  ←── NEW          │
│                                       ↙     ↘                   │
│                              (pass)           (fail → inv)       │
│                                        ↓                         │
│                                  update_memory → END             │
└──────────────────────────────────────────────────────────────────┘
       │              │                  │              │
       ▼              ▼                  ▼              ▼
┌──────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│ 记忆服务 │  │  工具服务     │  │  RAG 服务    │  │  MCP Server  │
│ Redis +  │  │ Code Sandbox │  │ ChromaDB +   │  │ (stdio/SSE)  │
│ Mem0     │  │ Log Query .. │  │ BGE-M3       │  │              │
└──────────┘  └──────────────┘  └──────────────┘  └──────────────┘
                            │
┌──────────────────────────────────────────────────────────────────┐
│  横切层                                                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐   │
│  │ Model Router │  │  Guardrails  │  │ LangSmith + Audit    │   │
│  │ (多模型/降级) │  │ (输入/输出)  │  │ (全链路 + 护栏日志) │   │
│  └──────────────┘  └──────────────┘  └──────────────────────┘   │
└──────────────────────────────────────────────────────────────────┘
```

### 2.2 v3.0 LangGraph 节点流程

```
START
  → retrieve_memory        (召回长期记忆)
  → retrieve_knowledge     (RAG 检索)
  → planner                (拆解步骤)
  → investigator           (调查执行)
    ├── [human_approval]   (HITL: 危险工具审批, interrupt_before)
    ├── tool_executor      (直连工具 / MCP Client)
    └── investigator       (循环)
  → reporter               (撰写报告)
  → critic                 (★ NEW: 自审查)
    ├── pass → update_memory
    └── fail → investigator (回退, 最多 2 次)
  → update_memory          (写入记忆)
  → END
```

### 2.3 目录结构（v3.0 增量）

```
deepinvestigate/
├── API/
│   ├── agent/
│   │   ├── graph.py              # ← 改造：加 checkpointer + interrupt + critic 路由
│   │   ├── state.py              # ← 改造：加 critic/hitl 相关字段
│   │   ├── sse_adapter.py        # ← 改造：支持 HITL 中断事件
│   │   ├── nodes/
│   │   │   ├── critic.py         # ★ NEW: Critic 审查节点
│   │   │   ├── human_approval.py # ★ NEW: HITL 审批节点（空壳，靠 interrupt）
│   │   │   └── ...               # 保留现有节点
│   │   └── prompts.py            # ← 改造：加 CRITIC_SYSTEM
│   │
│   ├── model_router/             # ★ NEW: 多模型路由
│   │   ├── __init__.py
│   │   ├── router.py             # 模型选择策略
│   │   ├── providers.py          # 各模型提供商适配
│   │   └── cost_tracker.py       # Token 用量与成本追踪
│   │
│   ├── guardrails/               # ★ NEW: 安全护栏
│   │   ├── __init__.py
│   │   ├── input_guard.py        # 输入敏感词检测
│   │   ├── output_guard.py       # 输出 PII 脱敏 + 安全扫描
│   │   └── audit.py              # 护栏审计日志
│   │
│   ├── mcp/                      # ★ NEW: MCP 集成
│   │   ├── __init__.py
│   │   ├── server.py             # MCP Server 封装（暴露 9 工具）
│   │   ├── client_node.py        # MCP Client LangGraph 节点
│   │   └── config.json           # MCP Server 配置
│   │
│   ├── a2a/                      # ★ NEW: Agent-to-Agent 协议
│   │   ├── __init__.py
│   │   ├── protocol.py           # A2A 消息格式定义
│   │   └── coordinator.py        # 多 Investigator 并行协调
│   │
│   ├── chat_api_v2.py            # ← 改造：加 session 恢复 + HITL resume 路由
│   ├── server_v2.py              # ← 改造：注册新路由
│   └── config.yaml               # ← 扩展：多模型 + 护栏 + MCP 配置
│
├── eval/
│   ├── dataset/
│   │   └── attack_logs_eval.jsonl # ← 扩展：15 → 50+ 条
│   ├── metrics.py                 # ← 改造：加 4 个新指标
│   └── run_eval.py                # ← 改造：支持 v2 vs v3 对比
│
├── docs/
│   ├── PRD_V3.md                  # ★ NEW
│   └── DESIGN_V3.md               # ★ NEW (本文档)
│
└── docker-compose.yml             # 不变
```

---

## 3. 核心模块设计

### 3.1 MCP 集成（FR-1）

#### 3.1.1 架构

```
                    ┌─────────────────────┐
                    │    MCP Server        │
                    │  (stdio / SSE)       │
                    │                      │
                    │  tools/              │
                    │  ├── run_python      │
                    │  ├── query_logs      │
                    │  ├── search_cve      │
                    │  ├── rag_search      │
                    │  ├── recall_memory   │
                    │  ├── web_search      │
                    │  ├── read_file       │
                    │  ├── write_file      │
                    │  └── list_files      │
                    └──────────┬──────────┘
                               │ MCP Protocol
                    ┌──────────┴──────────┐
                    │                     │
              ┌─────┴─────┐       ┌──────┴──────┐
              │ MCP Client │       │ MCP Client  │
              │ (本项目)   │       │ (外部项目)  │
              │ LangGraph  │       │ CrewAI etc  │
              │ Node       │       │             │
              └───────────┘       └─────────────┘
```

#### 3.1.2 MCP Server 设计

```python
# API/mcp/server.py
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("DeepInvestigate Tools")

@mcp.tool()
def run_python(code: str) -> str:
    """在沙箱中执行 Python 代码并返回输出"""
    from tools.code_executor import _execute
    return _execute(code)

@mcp.tool()
def query_logs(query: str, time_range: str = "24h") -> dict:
    """结构化日志查询"""
    from tools.log_query import _query
    return _query(query, time_range)

@mcp.tool()
def search_cve(cve_id: str = "", keyword: str = "") -> dict:
    """CVE 漏洞信息查询"""
    from tools.cve_search import _search
    return _search(cve_id=cve_id, keyword=keyword)

@mcp.tool()
def rag_search(query: str, top_k: int = 5) -> list:
    """知识库检索（MITRE ATT&CK / CVE）"""
    from tools.rag_search import _search
    return _search(query, top_k)

@mcp.tool()
def recall_memory(query: str, mem_type: str = "episodic") -> list:
    """长期记忆召回"""
    from tools.recall_memory import _recall
    return _recall(query, mem_type)

@mcp.tool()
def web_search(query: str) -> list:
    """网络搜索"""
    from tools.web_search import _search
    return _search(query)

@mcp.tool()
def read_file(path: str) -> str:
    """读取 workspace 文件"""
    from tools.file_io import _read
    return _read(path)

@mcp.tool()
def write_file(path: str, content: str) -> str:
    """写入文件"""
    from tools.file_io import _write
    return _write(path, content)

@mcp.tool()
def list_files(path: str = ".") -> list:
    """列出目录文件"""
    from tools.file_io import _list
    return _list(path)
```

启动方式：

```python
# 作为独立进程运行
# python -m API.mcp.server --transport stdio
# python -m API.mcp.server --transport sse --port 8202
```

#### 3.1.3 MCP Client 节点

```python
# API/mcp/client_node.py
from langchain_core.tools import StructuredTool
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

class MCPToolNode:
    """从 MCP Server 发现工具并封装为 LangChain Tool"""

    def __init__(self, server_params: StdioServerParameters):
        self.server_params = server_params
        self._tools: list[StructuredTool] = []

    async def discover(self) -> list[StructuredTool]:
        """连接 MCP Server，发现工具列表并转为 LangChain Tool"""
        async with stdio_client(self.server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools_result = await session.list_tools()
                self._tools = [
                    self._to_langchain_tool(t, session)
                    for t in tools_result.tools
                ]
        return self._tools

    def _to_langchain_tool(self, mcp_tool, session) -> StructuredTool:
        """MCP Tool → LangChain StructuredTool"""
        async def _call(**kwargs):
            result = await session.call_tool(mcp_tool.name, arguments=kwargs)
            return result.content[0].text
        return StructuredTool(
            name=mcp_tool.name,
            description=mcp_tool.description or "",
            coroutine=_call,
            args_schema=self._build_schema(mcp_tool.inputSchema),
        )
```

#### 3.1.4 双模式切换

```yaml
# config.yaml
mcp:
  enabled: false          # 默认直连模式
  servers:
    - name: "local-tools"
      transport: "stdio"
      command: "python"
      args: ["-m", "API.mcp.server"]
```

```python
# API/agent/graph.py 中的工具选择逻辑
def _get_tool_node():
    if config.mcp.enabled:
        return mcp_tool_executor  # MCP Client 节点
    return ToolNode(get_all_tools())  # 直连 ToolNode
```

---

### 3.2 Human-in-the-Loop（FR-2）

#### 3.2.1 设计原理

利用 LangGraph 的 `interrupt()` 机制：在 `tool_executor` 执行前检查工具风险等级，高风险工具触发中断，等待前端审批后通过 `Command(resume=...)` 恢复。

```
investigator → [interrupt_before="human_approval"]
                    ↓ (有 tool_calls 且工具为高风险)
              ┌─────────────┐
              │ 图暂停       │
              │ 前端弹审批卡 │
              └──────┬──────┘
                     ↓ Command(resume={"approved": True/False})
              ┌─────────────┐
              │ tool_executor│ (approved=True)
              │ 或跳过工具   │ (approved=False)
              └─────────────┘
```

#### 3.2.2 工具风险分级

```python
# API/agent/nodes/human_approval.py
TOOL_RISK_LEVELS = {
    # Level 0: 只读，无需审批
    "rag_search":      0,
    "recall_memory":   0,
    "list_files":      0,
    "read_file":       0,

    # Level 1: 需审批
    "run_python":      1,
    "write_file":      1,
    "web_search":      1,

    # Level 2: 高风险
    "query_logs":      2,   # 可能含写操作
    "search_cve":      2,   # 外网请求
}
```

#### 3.2.3 审批节点

```python
# API/agent/nodes/human_approval.py
def human_approval_node(state: AgentState) -> dict:
    """HITL 审批节点 — 靠 interrupt_before 触发，本节点为空壳"""
    # 实际逻辑在 graph.py 的 interrupt_before 中
    # 此处仅做透传，审批结果通过 Command(resume) 注入 state
    approval = state.get("_approval_result")
    if approval and approval.get("approved"):
        return {}  # 继续执行工具
    else:
        # 拒绝：移除 tool_calls，注入提示
        return {
            "messages": [AIMessage(
                content="操作已被用户拒绝，请尝试其他方式。",
                name="investigator"
            )],
        }
```

#### 3.2.4 图组装（含 interrupt）

```python
# API/agent/graph.py（关键改动）
def build_graph():
    g = StateGraph(AgentState)

    # ... 添加节点 ...

    # ★ HITL: 在 tool_executor 前插入 human_approval，设置 interrupt_before
    g.add_node("human_approval", human_approval_node)
    g.add_node("tool_executor", _get_tool_node())

    g.add_edge("investigator", "human_approval")
    g.add_conditional_edges(
        "human_approval",
        _route_after_approval,
        {"execute": "tool_executor", "skip": "investigator"}
    )
    g.add_edge("tool_executor", "investigator")

    return g.compile(
        checkpointer=checkpointer,
        interrupt_before=["human_approval"],  # ★ 在此节点前中断
    )
```

#### 3.2.5 前端审批流程

```
1. SSE 流中收到 on_chain_interrupt 事件 → 前端渲染审批卡片
2. 卡片内容：工具名、参数摘要、风险等级、Agent 调用理由
3. 用户点击"批准" → POST /chat/resume {thread_id, approved: true}
4. 用户点击"拒绝" → POST /chat/resume {thread_id, approved: false}
5. 后端调用 graph.astream(Command(resume=...), config) 恢复执行
```

```python
# API/chat_api_v2.py（新增路由）
@router.post("/chat/resume")
async def resume_chat(request: ResumeRequest):
    """HITL 审批恢复"""
    graph = get_graph()
    config = {"configurable": {"thread_id": request.thread_id}}

    async def event_stream():
        async for chunk in stream_agent_as_openai_sse(
            graph, None, model=request.model,
            config=config,
            resume={"approved": request.approved, "approve_all": request.approve_all}
        ):
            yield chunk

    return StreamingResponse(event_stream(), media_type="text/event-stream")
```

---

### 3.3 Checkpointing 与对话持久化（FR-3）

#### 3.3.1 Checkpointer 选型

使用 `langgraph.checkpoint.sqlite.SqliteSaver`，零外部依赖，适合本地开发与演示。

```python
# API/agent/graph.py
from langgraph.checkpoint.sqlite import SqliteSaver
import sqlite3

def _get_checkpointer():
    conn = sqlite3.connect("data/checkpoints.db", check_same_thread=False)
    return SqliteSaver(conn)

def build_graph():
    # ...
    return g.compile(
        checkpointer=_get_checkpointer(),
        interrupt_before=["human_approval"],
    )
```

#### 3.3.2 会话恢复

```python
# API/chat_api_v2.py
@router.post("/chat/completions")
async def chat_completions_v2(request: ChatCompletionRequest):
    thread_id = _make_thread_id(request.session_id)

    config = {"configurable": {"thread_id": thread_id}}

    if request.session_id:
        # 检查是否有历史状态
        graph = get_graph()
        try:
            history = graph.get_state(config)
            if history and history.values:
                logger.info("Resuming session %s", thread_id)
                # 有历史状态：直接继续流式
                init_state = None  # 不传 init_state，从 checkpoint 恢复
        except Exception:
            init_state = new_initial_state(...)
    else:
        init_state = new_initial_state(...)

    # 流式执行
    async def event_stream():
        async for chunk in stream_agent_as_openai_sse(
            graph, init_state, model=request.model, config=config
        ):
            yield chunk
    # ...
```

#### 3.3.3 时间旅行 API

```python
# API/chat_api_v2.py
@router.get("/threads/{thread_id}/history")
async def get_thread_history(thread_id: str):
    """获取会话的所有 checkpoint"""
    graph = get_graph()
    config = {"configurable": {"thread_id": thread_id}}

    history = []
    for checkpoint in graph.get_state_history(config):
        history.append({
            "checkpoint_id": checkpoint.config["configurable"]["checkpoint_id"],
            "timestamp": checkpoint.metadata.get("timestamp"),
            "node": checkpoint.metadata.get("source"),
            "step": checkpoint.metadata.get("step"),
        })
    return {"thread_id": thread_id, "history": history}

@router.get("/threads/{thread_id}/state")
async def get_thread_state(thread_id: str):
    """获取会话最新状态"""
    graph = get_graph()
    config = {"configurable": {"thread_id": thread_id}}
    state = graph.get_state(config)
    return {
        "thread_id": thread_id,
        "has_state": state is not None,
        "next_nodes": state.next if state else None,
        "values_preview": _preview_state(state.values) if state else None,
    }
```

#### 3.3.4 过期清理

```python
# API/agent/graph.py
import threading, time

def _cleanup_old_checkpoints(db_path: str, ttl_days: int = 7):
    """后台线程定期清理过期 checkpoint"""
    while True:
        time.sleep(3600)  # 每小时
        conn = sqlite3.connect(db_path)
        cutoff = time.time() - ttl_days * 86400
        conn.execute("DELETE FROM checkpoints WHERE created_at < ?", (cutoff,))
        conn.commit()
        conn.close()

# 启动时开启清理线程
threading.Thread(target=_cleanup_old_checkpoints, args=("data/checkpoints.db",), daemon=True).start()
```

---

### 3.4 Self-Reflection / Critic Agent（FR-4）

#### 3.4.1 设计原理

```
reporter → critic (独立 LLM, 温度 0.2)
              ↓
         ┌────┴────┐
    score≥4     score<4
         ↓           ↓
   update_memory  investigator (回退, 附 Critic 建议)
                       ↓
                  (最多回退 2 次)
```

#### 3.4.2 Critic 节点

```python
# API/agent/nodes/critic.py
CRITIC_SYSTEM = """你是 **DeepInvestigate-Critic**，一位严格的安全报告质量审查员。

## 审查维度（每项 1-5 分）
1. **事实准确性**：报告中的结论是否有工具输出/日志证据支撑？有无凭空捏造？
2. **逻辑完整性**：调查过程是否覆盖了所有计划步骤？有无遗漏关键环节？
3. **关键信息缺失**：是否遗漏了重要的攻击指标（IP、时间、漏洞编号）？
4. **建议可行性**：处置建议是否具体、可操作？还是泛泛而谈？

## 输出格式（严格 JSON）
{
  "scores": {
    "factual_accuracy": 4,
    "logical_completeness": 3,
    "info_completeness": 4,
    "actionability": 5
  },
  "overall": 4,
  "issues": ["未验证 IP 1.2.3.4 的地理位置", "缺少时间线可视化"],
  "suggestions": ["请补充 IP 归属地查询", "建议增加攻击时间线图表"]
}

## 评分标准
- overall ≥ 4: 通过，报告质量合格
- overall < 4: 不通过，需回退补充调查
"""

async def critic_node(state: AgentState) -> dict:
    """Critic 审查节点"""
    llm = get_critic_llm(temperature=0.2)  # 低温度保证审查稳定

    final_answer = state.get("final_answer") or ""
    messages = state.get("messages") or []

    # 构建审查上下文
    context = f"""## 待审查报告
{final_answer[:4000]}

## 调查过程摘要
{_summarize_messages(messages[-20:])}
"""
    resp = await llm.ainvoke([
        SystemMessage(content=CRITIC_SYSTEM),
        HumanMessage(content=context),
    ])

    # 解析 JSON
    try:
        review = json.loads(_extract_json(resp.content))
    except json.JSONDecodeError:
        review = {"overall": 4, "issues": [], "suggestions": []}

    overall = review.get("overall", 4)
    critic_count = state.get("critic_count", 0) + 1

    return {
        "critic_score": overall,
        "critic_feedback": review,
        "critic_count": critic_count,
    }


def route_after_critic(state: AgentState) -> Literal["pass", "retry"]:
    """Critic 后路由"""
    score = state.get("critic_score", 5)
    retries = state.get("critic_count", 0)

    if score >= 4 or retries >= 2:
        return "pass"  # 通过或已达最大重试
    return "retry"     # 回退调查
```

#### 3.4.3 图组装（Critic 部分）

```python
# API/agent/graph.py
g.add_node("critic", critic_node)

g.add_edge("reporter", "critic")
g.add_conditional_edges(
    "critic",
    route_after_critic,
    {
        "pass": "update_memory",
        "retry": "investigator",  # 回退，附 Critic 建议
    }
)
```

#### 3.4.4 回退时的上下文注入

```python
# API/agent/nodes/investigator.py（改造）
def _build_retry_brief(state: AgentState) -> str:
    """回退重试时的补充简报"""
    feedback = state.get("critic_feedback", {})
    suggestions = feedback.get("suggestions", [])
    issues = feedback.get("issues", [])

    return f"""## ⚠️ 报告审查未通过（评分: {feedback.get('overall')}/5）

**发现的问题**：
{chr(10).join(f'- {i}' for i in issues)}

**补充调查方向**：
{chr(10).join(f'- {s}' for s in suggestions)}

请针对以上问题进行补充调查，完成后重新输出中间结论。"""
```

---

### 3.5 多模型路由与成本追踪（FR-5）

#### 3.5.1 模型路由器

```python
# API/model_router/router.py
from dataclasses import dataclass
from enum import Enum
from typing import Optional

class ModelTier(Enum):
    HIGH = "high"       # GPT-4o / DeepSeek-V3
    MEDIUM = "medium"   # DeepSeek-Chat / GPT-4o-mini
    LOW = "low"         # DeepSeek-Chat / GPT-4o-mini

@dataclass
class ModelConfig:
    provider: str       # "deepseek" | "openai" | "claude"
    model_name: str
    api_key: str
    base_url: str
    tier: ModelTier
    max_rpm: int = 60   # 每分钟最大请求数

class ModelRouter:
    """多模型路由器"""

    def __init__(self, configs: list[ModelConfig]):
        self.configs = configs
        self._primary = {tier: self._find_primary(tier) for tier in ModelTier}
        self._fallback = {tier: self._find_fallback(tier) for tier in ModelTier}

    def get_llm(self, tier: ModelTier, temperature: float = 0.4):
        """获取指定 tier 的 LLM，自动 fallback"""
        primary = self._primary.get(tier)
        fallback = self._fallback.get(tier)

        if primary and self._is_available(primary):
            return self._build_llm(primary, temperature)

        if fallback and self._is_available(fallback):
            logger.warning("Model %s unavailable, fallback to %s",
                           primary.model_name if primary else "N/A",
                           fallback.model_name)
            return self._build_llm(fallback, temperature)

        raise RuntimeError(f"No available model for tier {tier}")

    def _build_llm(self, config: ModelConfig, temperature: float):
        if config.provider == "deepseek":
            from langchain_deepseek import ChatDeepSeek
            return ChatDeepSeek(
                model=config.model_name,
                api_key=config.api_key,
                temperature=temperature,
            )
        elif config.provider == "openai":
            from langchain_openai import ChatOpenAI
            return ChatOpenAI(
                model=config.model_name,
                api_key=config.api_key,
                base_url=config.base_url,
                temperature=temperature,
            )
        # ...
```

#### 3.5.2 各节点模型分配

```python
# API/agent/llm.py（改造）
from model_router.router import ModelRouter, ModelTier

_router: Optional[ModelRouter] = None

def get_router() -> ModelRouter:
    global _router
    if _router is None:
        _router = ModelRouter(_load_model_configs())
    return _router

def get_planner_llm(streaming: bool = False):
    return get_router().get_llm(ModelTier.HIGH, temperature=0.3)

def get_investigator_llm(streaming: bool = False):
    return get_router().get_llm(ModelTier.MEDIUM, temperature=0.4)

def get_reporter_llm(streaming: bool = False):
    return get_router().get_llm(ModelTier.HIGH, temperature=0.5)

def get_critic_llm(temperature: float = 0.2):
    return get_router().get_llm(ModelTier.LOW, temperature=temperature)
```

#### 3.5.3 成本追踪

```python
# API/model_router/cost_tracker.py
from dataclasses import dataclass, field
from datetime import datetime
import json

# 模型单价（$/1M tokens）
PRICING = {
    "deepseek-chat":       {"prompt": 0.14, "completion": 0.28},
    "deepseek-reasoner":   {"prompt": 0.55, "completion": 2.19},
    "gpt-4o":              {"prompt": 2.50, "completion": 10.00},
    "gpt-4o-mini":         {"prompt": 0.15, "completion": 0.60},
}

@dataclass
class UsageRecord:
    timestamp: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float
    node: str
    thread_id: str

class CostTracker:
    """Token 用量与成本追踪器"""

    def __init__(self, redis_client):
        self.redis = redis_client

    def record(self, record: UsageRecord):
        """记录一次 LLM 调用"""
        key = f"usage:{datetime.now().strftime('%Y%m%d')}"
        self.redis.lpush(key, json.dumps(record.__dict__))
        self.redis.expire(key, 86400 * 30)  # 保留 30 天

    def get_daily_stats(self, days: int = 7) -> dict:
        """获取最近 N 天的用量统计"""
        # 汇总各日期的 usage:* key
        stats = {"total_cost": 0, "total_tokens": 0, "by_model": {}, "by_node": {}}
        # ... 聚合逻辑
        return stats
```

#### 3.5.4 配置

```yaml
# config.yaml（扩展）
models:
  primary:
    provider: "deepseek"
    model: "deepseek-chat"
    api_key: "${DEEPSEEK_API_KEY}"
    base_url: "https://api.deepseek.com/v1"

  fallback:
    provider: "openai"
    model: "gpt-4o-mini"
    api_key: "${OPENAI_API_KEY}"
    base_url: "https://api.openai.com/v1"

  tiers:
    high:
      primary: "deepseek-chat"
      fallback: "gpt-4o"
    medium:
      primary: "deepseek-chat"
      fallback: "gpt-4o-mini"
    low:
      primary: "deepseek-chat"
      fallback: "gpt-4o-mini"
```

---

### 3.6 Guardrails 安全护栏（FR-6）

#### 3.6.1 输入护栏

```python
# API/guardrails/input_guard.py
import re
from typing import Optional, Tuple

# 敏感词列表（可配置）
DEFAULT_BLOCKED_PATTERNS = [
    r"(政治敏感|反动|颠覆)",
    r"(色情|淫秽|成人内容)",
    r"(暴力恐怖|极端主义)",
    # ... 可扩展
]

class InputGuard:
    """输入安全护栏"""

    def __init__(self, blocked_patterns: list[str] = None):
        self.patterns = blocked_patterns or DEFAULT_BLOCKED_PATTERNS

    def check(self, text: str) -> Tuple[bool, Optional[str]]:
        """检查输入是否安全
        Returns: (is_safe, reason)
        """
        for pattern in self.patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return False, f"输入包含敏感内容，匹配规则: {pattern}"
        return True, None
```

#### 3.6.2 输出护栏

```python
# API/guardrails/output_guard.py
import re

# PII 检测模式
PII_PATTERNS = {
    "phone_cn":     r"1[3-9]\d{9}",
    "id_card_cn":   r"\d{17}[\dXx]",
    "email":        r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
    "ip_address":   r"\b(?:\d{1,3}\.){3}\d{1,3}\b",
}

class OutputGuard:
    """输出安全护栏 + PII 脱敏"""

    def sanitize(self, text: str) -> str:
        """对输出文本做 PII 脱敏"""
        sanitized = text
        for name, pattern in PII_PATTERNS.items():
            sanitized = re.sub(
                pattern,
                self._mask(name),
                sanitized
            )
        return sanitized

    def _mask(self, pii_type: str) -> str:
        masks = {
            "phone_cn":     "[手机号已隐藏]",
            "id_card_cn":   "[身份证号已隐藏]",
            "email":        "[邮箱已隐藏]",
            "ip_address":   "[IP已隐藏]",
        }
        return masks.get(pii_type, "[已隐藏]")

    def check_safety(self, text: str) -> Tuple[bool, Optional[str]]:
        """输出内容安全扫描（复用 InputGuard 的规则）"""
        # 可扩展为更复杂的输出安全检测
        return True, None
```

#### 3.6.3 审计日志

```python
# API/guardrails/audit.py
import json, time
from dataclasses import dataclass

@dataclass
class AuditEvent:
    timestamp: str
    event_type: str        # "input_blocked" | "output_sanitized" | "hitl_approved" | "hitl_rejected"
    user_id: str
    thread_id: str
    detail: str
    original_preview: str  # 原始内容前 200 字符

class AuditLogger:
    """护栏审计日志"""

    def __init__(self, redis_client):
        self.redis = redis_client

    def log(self, event: AuditEvent):
        key = f"audit:{event.timestamp[:10]}"  # 按天分 key
        self.redis.lpush(key, json.dumps(event.__dict__, ensure_ascii=False))
        self.redis.expire(key, 86400 * 90)  # 保留 90 天

    def query(self, days: int = 7, event_type: str = None) -> list:
        """查询审计日志"""
        # ... 聚合查询逻辑
        pass
```

#### 3.6.4 在 API 层集成

```python
# API/chat_api_v2.py（改造）
from guardrails.input_guard import InputGuard
from guardrails.output_guard import OutputGuard
from guardrails.audit import AuditLogger, AuditEvent

_input_guard = InputGuard()
_output_guard = OutputGuard()
_audit = AuditLogger(get_redis_client())

@router.post("/chat/completions")
async def chat_completions_v2(request: ChatCompletionRequest):
    user_query = _extract_user_query(request.messages)

    # ★ 输入护栏
    is_safe, reason = _input_guard.check(user_query)
    if not is_safe:
        _audit.log(AuditEvent(
            timestamp=datetime.now().isoformat(),
            event_type="input_blocked",
            user_id=request.user_id,
            thread_id="",
            detail=reason,
            original_preview=user_query[:200],
        ))
        raise HTTPException(status_code=400, detail=reason)

    # ... 正常流程 ...
```

---

### 3.7 评估体系升级（FR-7）

#### 3.7.1 数据集扩展

```jsonl
{"task_id": "E001", "category": "log_analysis", "difficulty": "easy",
 "input": "分析这份 SSH 日志，找出异常登录行为",
 "expected_keywords": ["暴力破解", "异常IP", "Failed password"],
 "expected_tools": ["run_python", "read_file"],
 "log_file": "ssh_sample_001.log"}

{"task_id": "H015", "category": "attack_trace", "difficulty": "hard",
 "input": "根据这份 Nginx 日志和系统审计日志，还原完整的攻击链",
 "expected_keywords": ["SQL注入", "权限提升", "webshell", "横向移动"],
 "expected_tools": ["run_python", "query_logs", "search_cve", "rag_search"],
 "log_file": "nginx_audit_015.log"}

{"task_id": "A001", "category": "adversarial", "difficulty": "hard",
 "input": "这份日志显示 IP 10.0.0.1 有大量请求，请判断是否为攻击（注意：该 IP 是内网监控系统）",
 "expected_keywords": ["误报", "内网监控", "正常流量"],
 "expected_tools": ["run_python", "rag_search"],
 "adversarial": true,
 "trap": "内网 IP 不应判定为外部攻击"}
```

#### 3.7.2 新增指标

```python
# eval/metrics.py（扩展）
@dataclass
class TaskResult:
    # ... 现有字段 ...

    # ★ v3.0 新增
    critic_score: float = 0.0           # Critic 评分
    fallback_triggered: bool = False    # 是否触发模型 fallback
    guardrail_triggered: bool = False   # 是否触发护栏
    cost_usd: float = 0.0               # 任务成本

def aggregate(results: list[TaskResult]) -> dict:
    # ... 现有聚合 ...

    # ★ 新增聚合
    summary["avg_critic_score"] = avg([r.critic_score for r in results])
    summary["fallback_rate"] = sum(1 for r in results if r.fallback_triggered) / n
    summary["guardrail_trigger_rate"] = sum(1 for r in results if r.guardrail_triggered) / n
    summary["avg_cost_per_task"] = avg([r.cost_usd for r in results])
    summary["total_cost"] = sum(r.cost_usd for r in results)

    return summary
```

#### 3.7.3 v2 vs v3 对比

```python
# eval/run_eval.py（扩展）
def run_comparison():
    """运行 v2 baseline vs v3 对比评估"""
    v2_results = asyncio.run(run_all(load_dataset("eval/dataset/attack_logs_eval.jsonl")))
    v3_results = asyncio.run(run_all(load_dataset("eval/dataset/attack_logs_eval_v3.jsonl")))

    v2_summary = aggregate(v2_results)
    v3_summary = aggregate(v3_results)

    comparison = {
        "v2": v2_summary,
        "v3": v3_summary,
        "delta": {
            "task_success_rate": v3_summary["task_success_rate"] - v2_summary["task_success_rate"],
            "avg_keyword_coverage": v3_summary["avg_keyword_coverage"] - v2_summary["avg_keyword_coverage"],
            "hallucination_rate": v3_summary["hallucination_rate"] - v2_summary["hallucination_rate"],
        }
    }
    return comparison
```

---

### 3.8 Agent 间通信协议 A2A（FR-8）

#### 3.8.1 消息格式

```python
# API/a2a/protocol.py
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional
import uuid, time

class MessageType(Enum):
    TASK_ASSIGN = "task_assign"
    TASK_RESULT = "task_result"
    CLARIFICATION_REQUEST = "clarification_request"
    STATUS_UPDATE = "status_update"

@dataclass
class A2AMessage:
    sender: str              # "planner" | "investigator_1" | "investigator_2"
    receiver: str
    msg_type: MessageType
    payload: dict
    correlation_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    timestamp: float = field(default_factory=time.time)
```

#### 3.8.2 并行调查协调器

```python
# API/a2a/coordinator.py
import asyncio
from typing import Any

class ParallelCoordinator:
    """多 Investigator 并行调查协调器"""

    def __init__(self, max_workers: int = 3):
        self.max_workers = max_workers

    async def dispatch(self, tasks: list[dict], graph, base_state: dict) -> list[dict]:
        """将独立子任务分发给多个 Investigator 并行执行"""
        sem = asyncio.Semaphore(self.max_workers)

        async def run_subtask(task: dict) -> dict:
            async with sem:
                sub_state = {**base_state, "user_query": task["description"]}
                result = await graph.ainvoke(sub_state)
                return {
                    "task_id": task["id"],
                    "result": result.get("final_answer", ""),
                }

        results = await asyncio.gather(*[run_subtask(t) for t in tasks])
        return results
```

#### 3.8.3 在 Planner 中启用并行

```python
# API/agent/nodes/planner.py（改造）
PLANNER_SYSTEM_V3 = """...
## 并行调查
如果任务可拆分为多个独立子任务（如同时分析多份日志、同时查询多个 CVE），
请在 plan 中用 `[PARALLEL]` 前缀标记可并行的步骤组：
{
  "plan": [
    "[PARALLEL]",
    "1. 分析 SSH 日志中的异常登录",
    "2. 分析 Nginx 日志中的异常请求",
    "[/PARALLEL]",
    "3. 汇总两份日志的分析结果"
  ]
}
"""
```

---

## 4. 状态对象扩展

```python
# API/agent/state.py（v3.0 扩展）
class AgentState(TypedDict, total=False):
    # ---- v2.0 保留 ----
    user_query: str
    thread_id: str
    user_id: str
    workspace_dir: str
    messages: Annotated[List[AnyMessage], add_messages]
    plan: Optional[List[str]]
    current_step: int
    retrieved_knowledge: List[Dict[str, Any]]
    recalled_memories: List[Dict[str, Any]]
    final_answer: Optional[str]
    generated_files: List[str]
    iteration_count: int
    max_iterations: int
    error: Optional[str]

    # ---- v3.0 新增 ----
    # HITL
    hitl_pending: bool                     # 是否有待审批操作
    hitl_tool_name: Optional[str]          # 待审批工具名
    hitl_tool_args: Optional[dict]         # 待审批工具参数
    hitl_risk_level: int                   # 风险等级
    _approval_result: Optional[dict]       # 审批结果（内部字段）

    # Critic
    critic_score: Optional[float]          # Critic 评分
    critic_feedback: Optional[dict]        # Critic 详细反馈
    critic_count: int                      # 回退次数

    # Model Router
    model_tier: Optional[str]              # 当前使用的模型 tier
    fallback_triggered: bool               # 是否触发 fallback

    # Guardrails
    guardrail_triggered: bool              # 是否触发护栏

    # A2A
    a2a_messages: List[dict]               # Agent 间消息
    parallel_tasks: Optional[list]         # 并行子任务列表
```

---

## 5. 配置扩展

```yaml
# config.yaml（v3.0 完整版）
api:
  base: "https://api.deepseek.com/v1"
  model_path: "deepseek-chat"
  api_key: "${DEEPSEEK_API_KEY}"

# ★ v3.0: 多模型配置
models:
  tiers:
    high:
      primary: "deepseek-chat"
      fallback: "gpt-4o"
    medium:
      primary: "deepseek-chat"
      fallback: "gpt-4o-mini"
    low:
      primary: "deepseek-chat"
      fallback: "gpt-4o-mini"
  providers:
    deepseek:
      api_key: "${DEEPSEEK_API_KEY}"
      base_url: "https://api.deepseek.com/v1"
    openai:
      api_key: "${OPENAI_API_KEY}"
      base_url: "https://api.openai.com/v1"

# ★ v3.0: MCP 配置
mcp:
  enabled: false
  servers:
    - name: "local-tools"
      transport: "stdio"
      command: "python"
      args: ["-m", "API.mcp.server"]

# ★ v3.0: HITL 配置
hitl:
  enabled: true
  risk_levels:
    "0": ["rag_search", "recall_memory", "list_files", "read_file"]
    "1": ["run_python", "write_file", "web_search"]
    "2": ["query_logs", "search_cve"]

# ★ v3.0: Guardrails 配置
guardrails:
  input:
    enabled: true
    blocked_patterns: []
  output:
    pii_masking: true
    safety_scan: true

# ★ v3.0: Checkpointing
checkpoint:
  db_path: "data/checkpoints.db"
  ttl_days: 7

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
  project: "DeepInvestigate-v3"
  api_key: "${LANGSMITH_API_KEY}"

agent:
  max_iterations: 15
  recursion_limit: 30
  default_temperature: 0.4
  critic_max_retries: 2
```

---

## 6. API 路由汇总

| 方法 | 路径 | 说明 | 变更 |
|---|---|---|---|
| POST | `/chat/completions` | 主聊天接口（OpenAI 兼容） | 改造：支持 session 恢复 |
| POST | `/chat/resume` | HITL 审批恢复 | ★ NEW |
| GET | `/threads/{id}/history` | 会话 checkpoint 历史 | ★ NEW |
| GET | `/threads/{id}/state` | 会话最新状态 | ★ NEW |
| GET | `/admin/usage` | Token 用量与成本 | ★ NEW |
| GET | `/admin/audit` | 护栏审计日志 | ★ NEW |
| GET | `/agent/health` | Agent 健康检查 | 改造：加新模块状态 |
| GET | `/files/{fid}/content` | 文件下载 | 不变 |

---

## 7. 关键流程

### 7.1 端到端流程（含所有新模块）

```
1. 用户输入 → InputGuard 检查 → 通过

2. retrieve_memory → retrieve_knowledge → planner
   (ModelRouter: HIGH tier)

3. investigator 循环
   (ModelRouter: MEDIUM tier)
   ├─ 有 tool_calls →
   │   ├─ ToolRiskLevel ≥ 1 → interrupt_before human_approval
   │   │   ├─ 前端弹审批卡片
   │   │   ├─ 用户批准 → tool_executor (直连/MCP)
   │   │   └─ 用户拒绝 → 跳过工具，告知 Agent
   │   └─ ToolRiskLevel = 0 → tool_executor 直接执行
   └─ 无 tool_calls → reporter

4. reporter (ModelRouter: HIGH tier) → 生成报告

5. critic (ModelRouter: LOW tier)
   ├─ score ≥ 4 → update_memory
   └─ score < 4 → investigator (回退, 附建议, 最多 2 次)

6. update_memory → OutputGuard.sanitize → 返回前端

7. 全程 LangSmith 追踪 + CostTracker 记录 + AuditLogger 记录
```

### 7.2 HITL 审批流程

```
[investigator 输出 tool_calls]
        ↓
[human_approval 节点前 interrupt]
        ↓
[SSE: on_chain_interrupt 事件 → 前端]
        ↓
[前端渲染审批卡片: 工具名 + 参数 + 风险等级]
        ↓
[用户操作]
   ├─ 批准 → POST /chat/resume {approved: true}
   │           → Command(resume) → tool_executor → investigator
   ├─ 拒绝 → POST /chat/resume {approved: false}
   │           → Command(resume) → 跳过工具 → investigator
   └─ 批准全部 → POST /chat/resume {approved: true, approve_all: true}
                 → 后续同类工具自动通过
```

---

## 8. 新增依赖

```
# requirements-v3.txt
# MCP
mcp>=1.0.0

# Checkpointing (已含在 langgraph 中)
# langgraph 自带 SqliteSaver

# 多模型
langchain-openai>=0.2.0
langchain-deepseek>=0.1.0

# Guardrails（轻量自研，无额外依赖）
# 如需更强大方案可接入:
# guardrails-ai>=0.5.0

# 评估扩展（无新依赖，复用现有）
```

---

## 9. 实施计划

按依赖关系分 4 个里程碑：

### M1：基础设施 + 快速见效（FR-3 + FR-5 部分）

- [ ] SqliteSaver Checkpointer 接入 `graph.py`
- [ ] 会话恢复 API（`/threads/{id}/history`, `/threads/{id}/state`）
- [ ] ModelRouter 基础框架 + config.yaml 扩展
- [ ] 各 Agent 节点切换到 ModelRouter
- [ ] CostTracker 基础实现

### M2：Agent 深度（FR-2 + FR-4）

- [ ] 工具风险分级 + `human_approval` 节点
- [ ] `interrupt_before` + `/chat/resume` 路由
- [ ] 前端审批卡片组件
- [ ] Critic 节点 + 条件回退路由
- [ ] CRITIC_SYSTEM prompt + 回退上下文注入

### M3：前沿 + 安全（FR-1 + FR-6）

- [ ] MCP Server 封装 9 工具
- [ ] MCP Client 节点 + 双模式切换
- [ ] InputGuard + OutputGuard
- [ ] AuditLogger + `/admin/audit` API
- [ ] 在 `chat_api_v2.py` 中集成护栏

### M4：收尾（FR-7 + FR-8 + 联调）

- [ ] 评估数据集扩展到 50+ 条
- [ ] 新增 4 个评估指标
- [ ] v2 vs v3 对比报告
- [ ] A2A 协议 + 并行调查协调器
- [ ] 全链路联调 + 文档更新

---

## 10. 风险与缓解

| 风险 | 概率 | 影响 | 缓解措施 |
|---|---|---|---|
| LangGraph `interrupt` 与 SSE 流式冲突 | 中 | 高 | 先做非流式 HITL，流式作为 stretch goal |
| MCP Python SDK API 不稳定 | 中 | 中 | 优先 stdio 传输，SSE 作为可选项 |
| 多模型 API 返回格式差异 | 中 | 中 | 统一封装为 OpenAI 兼容接口 |
| Critic 回退导致无限循环 | 低 | 高 | 硬限制最多 2 次回退 |
| Checkpoint 数据膨胀 | 低 | 中 | TTL 7 天自动清理 + 手动删除 API |
| A2A 过度设计 | 中 | 低 | 先做最小可用版本，不引入消息队列 |

---

## 11. 验收标准

### 功能验收

- [ ] MCP Server 可被 MCP Inspector 发现并调用
- [ ] 危险工具调用时前端弹出审批卡片
- [ ] 同一 session_id 多次请求共享 Agent 状态
- [ ] Critic 评分 < 4 时自动回退补充调查
- [ ] 主模型不可用时自动 fallback
- [ ] 输入含敏感词时被拦截
- [ ] 输出含 PII 时自动脱敏
- [ ] 评估集 ≥ 50 条，含对抗样本

### 性能验收

- [ ] 直连工具调用性能不退化（与 v2.0 持平）
- [ ] MCP 模式额外延迟 ≤ 50ms
- [ ] Checkpointing 写入不阻塞 Agent 主流程

### 质量验收

- [ ] 50 条测试集任务成功率 ≥ 80%
- [ ] 幻觉率 ≤ 10%
- [ ] Critic 评分均值 ≥ 3.5

---

## 12. 附录

### 12.1 与 v2.0 DESIGN.md 的关系

本文档是 v2.0 [DESIGN.md](./DESIGN.md) 的**增量升级**设计。v2.0 中已稳定的模块（记忆四层、RAG 流程、工具实现细节）不再重复，仅描述变更部分。

### 12.2 关键术语

- **MCP**：Model Context Protocol，Anthropic 提出的 LLM-工具标准协议
- **HITL**：Human-in-the-Loop，人在回路中的人工审批机制
- **Checkpointing**：图状态快照持久化，支持断点续跑
- **Critic**：自审查 Agent，对输出质量进行评分与纠错
- **A2A**：Agent-to-Agent，Agent 间显式通信协议
- **Guardrails**：安全护栏，对 LLM 输入输出做安全检测与脱敏

---

**文档版本**：v1.0  
**作者**：DeepInvestigate Team  
**最后更新**：2026-06-04  
**状态**：待评审 → 评审通过后进入实施  
**前置文档**：[PRD_V3.md](./PRD_V3.md)  
**关联文档**：[DESIGN.md](./DESIGN.md)（v2.0 架构设计）
