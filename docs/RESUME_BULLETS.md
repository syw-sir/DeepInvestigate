# DeepInvestigate v3.0 — 简历素材

## 📌 项目名建议

> **DeepInvestigate — 基于 LangGraph 的生产级多智能体安全调查系统**

按岗位定制：

| 岗位方向 | 推荐项目名 |
|---|---|
| 智能体开发 | **基于 LangGraph 的四 Agent 协作调查系统（DeepInvestigate）** |
| AI 应用开发 | **DeepInvestigate · 融合 RAG + 记忆 + 工具调用的全栈 AI 调查平台** |
| 大模型应用 | **DeepInvestigate · 带 HITL 与安全护栏的 LLM Agent 生产级应用** |

---

## 🎯 简历正文（推荐版本）

> **DeepInvestigate · 基于 LangGraph 的生产级多智能体安全调查系统** · 个人项目 · [GitHub 链接]
>
> - 基于 **LangGraph** 构建 **Planner → Investigator → Reporter → Critic** 四 Agent 协作架构，实现安全日志的自主调查、攻击路径推理与报告质量自审查
> - 设计 **CodeAct + ReAct** 混合推理范式，Agent 通过 **OpenAI Function Calling** 标准协议自主调用 **9 类工具**（Python 沙箱、日志查询、CVE 检索、RAG 知识库、长期记忆召回等）
> - 实现 **Human-in-the-Loop 审批机制**：基于 LangGraph `interrupt()` 对危险工具（代码执行 / 文件写入 / 外网请求）按三级风险动态拦截，前端弹审批卡片，支持批准/拒绝/会话级自动放行
> - 引入 **Critic 自审查 Agent**：对 Reporter 输出进行四维评分（事实准确性 / 逻辑完整性 / 信息完整度 / 建议可行性），评分 < 4 自动回退 Investigator 补充调查，形成"调查→报告→审查→修正"闭环
> - 基于 **SQLite Checkpointer** 实现会话持久化与断点续跑，支持 `get_state_history` 时间旅行调试；通过 **SSE 适配器**将 LangGraph 事件流映射为 OpenAI 兼容 chunk，含 HITL 中断事件
> - 集成 **RAG 检索增强**（ChromaDB + BGE-M3 Embedding），融合 MITRE ATT&CK / CVE 知识库；基于 **Redis Stack** 构建四层记忆架构（工作 / 情景 / 语义 / 程序），接入 **Mem0** 完成记忆自动抽取与合并
> - 实现**多模型路由**：按 Agent 角色分配模型（Planner/Reporter 用高能力模型，Critic 用低成本模型），主模型不可用时自动 fallback，附带 Token 用量与成本追踪
> - 构建**安全护栏**：输入敏感词拦截 + 输出 PII 脱敏（手机号/身份证/邮箱/IP）+ 护栏审计日志持久化
> - 工具封装为 **MCP Server**（Model Context Protocol），支持跨项目复用；设计 **A2A 协议**支持多 Investigator 并行调查与结果汇总
> - 自研评估体系（10 类指标 / 按难度分级 / 含对抗样本），支持 v2 vs v3 量化对比；全链路 LangSmith 追踪
> - 全栈实现：Python 3.12 · FastAPI · LangGraph · LangChain · Redis Stack · ChromaDB · Mem0 · MCP · Docker Compose · Next.js 14 · TypeScript · shadcn/ui

---

## 🎯 精简版（适合简历空间有限）

> **DeepInvestigate · 基于 LangGraph 的生产级多智能体安全调查系统** · 个人项目
>
> - 基于 **LangGraph** 构建 Planner → Investigator → Reporter → **Critic** 四 Agent 协作架构，实现安全日志自主调查与报告质量自审查
> - 实现 **HITL 人工审批**（三级风险动态拦截）+ **SQLite Checkpointer**（会话持久化与时间旅行）+ **多模型路由**（按角色分配 + 自动 fallback + 成本追踪）
> - 集成 **RAG**（ChromaDB + BGE-M3）+ **四层记忆**（Redis Stack + Mem0）+ **安全护栏**（输入拦截 + PII 脱敏 + 审计日志）
> - 工具封装为 **MCP Server** 支持跨项目复用；设计 **A2A 协议**支持多 Agent 并行调查
> - 自研评估体系（10 指标 / 对抗样本）+ LangSmith 全链路追踪
> - 全栈：FastAPI · LangGraph · Redis Stack · ChromaDB · MCP · Docker · Next.js 14 · TypeScript · shadcn/ui

---

## 🛠 完整技术栈关键词清单

### Agent / LLM
- LangGraph · LangChain · LangSmith · Mem0
- DeepSeek API · OpenAI API · Function Calling · ReAct · CodeAct
- Multi-Agent · Planner · Investigator · Reporter · Critic
- HITL (Human-in-the-Loop) · interrupt · Command · Checkpointer
- Streaming · SSE · Recursion Limit · Time Travel

### 工具与协议
- MCP (Model Context Protocol) · MCP Server · MCP Client
- A2A (Agent-to-Agent) · ParallelCoordinator
- Python Sandbox · Code Executor · Tool Use · ToolNode

### 存储
- Redis Stack · RediSearch · RedisJSON · HNSW · Vector Index
- ChromaDB · Cosine Similarity · BGE-M3 · Sentence Transformers
- SQLite · Checkpointing · State Persistence

### 安全
- Guardrails · Input Guard · Output Guard · PII Masking
- Audit Log · Risk Level · Sandbox Isolation

### 后端
- Python 3.12 · FastAPI · Pydantic v2 · asyncio · ContextVar
- SSE (Server-Sent Events) · CORS · Uvicorn

### 前端
- Next.js 14 · React 18 · TypeScript 5
- TailwindCSS · shadcn/ui · Radix UI · Monaco Editor · Recharts

### 工程化
- Docker Compose · Conda · pnpm · Model Router · Cost Tracker
- 自研评估指标（Keyword Coverage / Tool Call Accuracy / Hallucination Rate / Critic Score / Fallback Rate / Cost per Task）

---

## 💬 面试常见问题（v3.0 更新）

### Q1: 为什么用 LangGraph 而不是 LangChain AgentExecutor？

> "LangChain 的 AgentExecutor 把流程黑盒化了，难以做条件分支和回环。LangGraph 是显式的 StateGraph，节点 + 条件边 + 状态共享，**完全契合我的 Multi-Agent 切换和 Critic 回退逻辑**。而且 LangGraph 原生支持 `astream_events`、`interrupt()`、`Checkpointer`，这三个能力分别支撑了我的流式输出、HITL 审批和会话持久化，用其他框架需要大量胶水代码。"

### Q2: 四个 Agent 角色为什么这么切分？

> "Planner 用低温度（0.3）保证规划稳定，输出严格 JSON；Investigator 中等温度（0.4）平衡探索与稳定，绑定工具做实际调查；Reporter 高温度（0.5）让报告语言更自然；Critic 低温度（0.2）保证审查一致性。**四者共享 messages 历史**，但通过 system prompt 隔离职责。比 Supervisor 架构更轻量、token 成本更低，比单 Agent 在复杂任务上成功率更高。"

### Q3: HITL 是怎么实现的？为什么不用全局 interrupt_before？

> "第一版用了 `interrupt_before=['human_approval']`，但发现**所有工具都会被拦截**，包括安全的 `rag_search`。后来改为在 `_human_approval_node` 内部用 `interrupt()` 按风险等级条件触发：Level 0 工具（只读查询）直接放行，Level 1-2 工具（代码执行、文件写入、外网请求）才暂停等审批。这样安全工具零开销，危险工具有兜底。"

### Q4: Critic Agent 回退会不会导致无限循环？

> "硬限制最多回退 2 次。Critic 评分 < 4 时，将审查建议作为补充调查方向注入 Investigator 的上下文，Agent 针对性地补充调查后重新生成报告。超过 2 次则强制通过并标记'未经充分审查'。实际测试中大部分任务 0-1 次回退即可通过。"

### Q5: Checkpointing 怎么用的？

> "用 LangGraph 自带的 `SqliteSaver`，零外部依赖。每次图执行后自动保存 checkpoint，通过 `thread_id` 恢复历史会话。还暴露了 `/threads/{id}/history` API 做时间旅行——可以查看每次节点执行前后的状态快照，调试时非常有用。"

### Q6: 多模型路由的策略是什么？

> "按角色分配：Planner 和 Reporter 用高能力模型（DeepSeek-Chat），Investigator 用中等模型，Critic 用低成本模型（可配 GPT-4o-mini）。主模型连续失败 3 次自动标记不可用，60 秒冷却后重试。每次调用记录 Token 用量和成本，提供 `/admin/usage` 查询接口。"

### Q7: MCP 在你的项目里怎么用的？

> "把 9 个工具封装成 MCP Server，支持 stdio 和 SSE 两种传输。LangGraph 中通过配置开关在'直连 ToolNode'和'MCP Client 节点'之间切换。直连模式零性能损耗，MCP 模式让工具可被任何支持 MCP 的外部 Agent 框架（如 CrewAI、AutoGen）复用。"

### Q8: Guardrails 覆盖了哪些场景？

> "三层：输入层用正则拦截敏感内容（可配置黑名单）；输出层对 PII（手机号、身份证、邮箱、IP）自动脱敏替换为占位符；审计层将所有拦截事件写入 Redis 持久化，支持按时间和类型查询。"

### Q9: 评估体系怎么设计的？

> "10 个指标，按难度（easy/medium/hard）和类别（日志分析/漏洞调查/攻击溯源/威胁情报/合规检查）分组。包含对抗样本（误导信息、不完整日志、矛盾数据）测试 Agent 鲁棒性。每次重大改动跑回归，自动生成 v2 vs v3 对比报告。"

### Q10: 这套系统怎么进一步扩展？

> 1. **接知识图谱**：用 Neo4j 存资产-漏洞-攻击关系，Agent 走图查询做路径推理
> 2. **真沙箱**：把 `run_python` 换成 Docker/nsjail，支持多语言
> 3. **Prompt 版本管理**：引入 Prompt Registry + A/B 测试
> 4. **RAG 评估**：接入 RAGAS 评估检索质量
> 5. **多模态**：支持 PDF/图片输入的安全报告分析

---

## 📊 可量化数据点（跑过 eval 后填上具体数字）

执行 `python -m eval.run_eval` 后，可写入简历的真实数字：

- 任务成功率（v2 baseline vs v3 对比）
- 任务平均完成时间
- Critic 评分均值
- 重复任务通过记忆复用的迭代轮数下降比例
- 关键词覆盖率提升幅度
- 幻觉率
- 模型 Fallback 触发频率
- 单任务平均成本（USD）
