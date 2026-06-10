# DeepInvestigate v4.1 — 简历素材

## 📌 项目名建议

> **DeepInvestigate — 基于 LangGraph 的生产级多智能体自主安全调查与处置系统**

按岗位定制：

| 岗位方向 | 推荐项目名 |
|---|---|
| 智能体开发 | **基于 LangGraph 的四 Agent 协作自主调查系统（DeepInvestigate）** |
| AI 应用开发 | **DeepInvestigate · 融合自主取证 + RAG + 记忆 + 处置闭环的全栈 AI 调查平台** |
| 大模型应用 | **DeepInvestigate · 带 HITL 审批与处置回滚的 LLM Agent 生产级应用** |

---

## 🎯 简历正文（推荐版本 — 针对智能体开发岗位）

> **DeepInvestigate · 基于 LangGraph 的生产级多智能体自主安全调查与处置系统** · 个人项目 · [GitHub 链接]
>
> - 基于 **LangGraph** 构建 **Planner → Investigator → Reporter → Critic** 四 Agent 协作架构，外加闲聊快捷路由，实现主机安全的自主调查、威胁处置与报告质量自审查
> - **v4.0 自主取证**：封装 **8 个主机取证工具**（进程扫描 / 网络连接 / 登录审计 / 启动项检查 / 注册表扫描 / 文件完整性 / Defender 日志 / 系统信息），Agent 自主调用 PowerShell 采集主机数据，不再等用户喂日志
> - **v4.1 处置闭环**：实现 **6 个处置工具**（kill_process / quarantine_file / block_ip / remove_startup / repair_registry / rollback_action），每个操作前自动备份（JSON / .reg / XML），支持一键回滚
> - 实现 **Human-in-the-Loop 审批机制**：工具分三级风险，仅 Level 3 处置工具触发 LangGraph `interrupt()`，前端 SSE 流中检测中断标记 → **渲染交互式审批卡片**（工具名 + 风险等级 + 批准/拒绝按钮）→ 调 `/chat/resume` 恢复执行
> - 设计**非管理员优雅降级**：检测工具在无管理员权限时自动回退（Get-NetTCPConnection → netstat -ano；Get-Process -IncludeUserName → 基础 Get-Process），确保普通用户下调查流程不中断
> - 引入 **Critic 自审查 Agent**：对 Reporter 输出进行 **7 维评分**（事实准确性 / 逻辑完整性 / 证据充分性 / 关键信息缺失 / 建议可行性 / 处置安全性 / 处置完整性），评分 < 4 自动回退 Investigator 补充调查，最多 2 次
> - 基于 **SQLite Checkpointer** 实现会话持久化与断点续跑，支持 `get_state_history` 时间旅行调试；通过 **SSE 适配器**将 LangGraph 事件流映射为 OpenAI 兼容 chunk，含 HITL 中断事件 + final_answer 补偿机制
> - 集成 **RAG 检索增强**（ChromaDB + OpenAI Embedding），融合 MITRE ATT&CK / CVE 知识库；基于 **Redis Stack** 构建四层记忆架构（工作 / 情景 / 语义 / 程序），接入 **Mem0** 完成记忆自动抽取
> - 实现**多模型路由**：按 Agent 角色分配模型（Planner/Reporter 用高能力模型，Critic 用低成本模型），主模型不可用时自动 fallback，附带 Token 用量与成本追踪
> - 构建**安全护栏**：输入敏感词拦截 + 输出 PII 脱敏 + 护栏审计日志持久化；**代码沙箱**安全策略精细化（允许 subprocess.run 列表参数，禁止 shell=True）
> - 全栈实现：Python 3.10 · FastAPI · LangGraph · LangChain · Redis Stack · ChromaDB · Mem0 · MCP · Docker Compose · Next.js 14 · TypeScript · shadcn/ui

---

## 🎯 精简版（适合简历空间有限）

> **DeepInvestigate · 基于 LangGraph 的自主安全调查与处置系统** · 个人项目
>
> - 基于 **LangGraph** 构建 Planner → Investigator → Reporter → **Critic** 四 Agent 协作架构，实现主机安全自主调查与威胁处置
> - **v4.0/4.1**：封装 **14 个主机工具**（8 取证 + 6 处置），Agent 自主采集系统信息并执行威胁处置，每次操作自动备份支持回滚
> - 实现 **HITL 人工审批**（三级风险 + 前端审批卡片 UI）+ **SQLite Checkpointer**（会话持久化与时间旅行）+ **多模型路由**（按角色分配 + 自动 fallback + 成本追踪）
> - 设计**非管理员优雅降级**（netstat 回退 / Get-Process 降级），保证普通权限下调查流程可用
> - 集成 **RAG**（ChromaDB）+ **四层记忆**（Redis Stack + Mem0）+ **安全护栏**（输入拦截 + PII 脱敏 + 审计日志）
> - 工具封装为 **MCP Server** 支持跨项目复用；设计 **A2A 协议**支持多 Agent 并行调查
> - 自研评估体系（10 指标 / 对抗样本）+ LangSmith 全链路追踪
> - 全栈：FastAPI · LangGraph · Redis Stack · ChromaDB · MCP · Docker · Next.js 14 · TypeScript · shadcn/ui

---

## 🛠 完整技术栈关键词清单

### Agent / LLM
- LangGraph · LangChain · LangSmith · Mem0
- DeepSeek API · OpenAI API · Function Calling · ReAct · CodeAct
- Multi-Agent · Planner · Investigator · Reporter · Critic · ChatResponder
- HITL (Human-in-the-Loop) · interrupt · Command · Checkpointer · /chat/resume
- Streaming · SSE · Recursion Limit · Time Travel · final_answer fallback

### v4.0 / v4.1 主机取证与处置
- PowerShell Automation · Get-Process · netstat · Get-Service · Get-ScheduledTask
- Registry Scan · File Integrity · ADS Detection · Windows Defender Logs
- Process Termination · File Quarantine · Firewall Blocking · Startup Removal
- Registry Repair · Action Rollback · Audit Trail · Non-Admin Fallback

### 工具与协议
- MCP (Model Context Protocol) · MCP Server · MCP Client
- A2A (Agent-to-Agent) · ParallelCoordinator
- Python Sandbox · Code Executor · Tool Use · ToolNode
- Subprocess Security · Static Analysis · Dangerous Pattern Detection

### 存储
- Redis Stack · RediSearch · RedisJSON · HNSW · Vector Index
- ChromaDB · Cosine Similarity · OpenAI Embedding
- SQLite · Checkpointing · State Persistence

### 安全
- Guardrails · Input Guard · Output Guard · PII Masking
- Audit Log · Risk Level (0-3) · Sandbox Isolation
- Forensics Backup · Registry Export · Rollback Mechanism

### 后端
- Python 3.10 · FastAPI · Pydantic v2 · asyncio · ContextVar
- SSE (Server-Sent Events) · CORS · Uvicorn · httpx

### 前端
- Next.js 14 · React 18 · TypeScript 5
- TailwindCSS · shadcn/ui · Radix UI · Monaco Editor · Recharts
- HITL Approval Card · Streaming SSE Reader · Interactive Buttons

### 工程化
- Docker Compose · pnpm · Model Router · Cost Tracker · YAML Config
- 自研评估指标（Keyword Coverage / Tool Call Accuracy / Hallucination Rate / Critic Score / Fallback Rate / Cost per Task）

---

## 💬 面试常见问题（v4.1 更新）

### Q1: 为什么用 LangGraph 而不是 LangChain AgentExecutor？

> "LangChain 的 AgentExecutor 把流程黑盒化了，难以做条件分支和回环。LangGraph 是显式的 StateGraph，节点 + 条件边 + 状态共享，**完全契合我的 Multi-Agent 切换和 Critic 回退逻辑**。而且 LangGraph 原生支持 `astream_events`、`interrupt()`、`Checkpointer`，这三个能力分别支撑了我的流式输出、HITL 审批和会话持久化。我的闲聊快捷路由也是用 LangGraph 的条件边实现的——`_route_from_start` 检测到问候语直接跳 chat_responder 节点，避免完整流水线开销。"

### Q2: 四个 Agent 角色为什么这么切分？

> "Planner 用低温度（0.3）保证规划稳定，输出严格 JSON；Investigator 中等温度（0.4）平衡探索与稳定，绑定 23 个工具做实际调查；Reporter 高温度（0.5）让报告语言更自然；Critic 低温度（0.2）保证审查一致性。**四者共享 messages 历史**，但通过 system prompt 隔离职责。比 Supervisor 架构更轻量、token 成本更低，比单 Agent 在复杂任务上成功率更高。v4.1 的 Critic 审查维度从 4 个扩展到 7 个，专门增加了处置安全性和处置完整性的评估。"

### Q3: HITL 是怎么实现的？为什么不是所有工具都触发审批？

> "工具分三级风险：Level 0 只读查询直接放行，Level 1-2 取证工具（scan_processes / check_network 等）自动放行以保证调查流程顺畅，只有 Level 3 处置工具（kill_process / block_ip 等）才触发 LangGraph `interrupt()`。第一版用 `interrupt_before` 全局拦截，发现安全工具也被卡了，后来改成在 `_human_approval_node` 内部用 `interrupt()` 按风险等级条件触发。审批消息通过 SSE 流推给前端，前端检测到 '需要人工审批' 后展示交互式卡片——上面有工具名、风险等级、批准/拒绝按钮。点批准后 POST /chat/resume 继续执行。"

### Q4: Critic Agent 回退会不会导致无限循环？

> "硬限制最多回退 2 次。Critic 7 维评分 < 4 时，将审查建议作为补充调查方向注入 Investigator 的上下文，Agent 针对性地补充调查后重新生成报告。超过 2 次则强制通过并标记。实际测试中大部分任务 0-1 次回退即可通过。"

### Q5: Checkpointing 怎么用的？

> "用 LangGraph 自带的 `AsyncSqliteSaver`，零外部依赖。每次图执行后自动保存 checkpoint，通过 `thread_id` 恢复历史会话。还暴露了 `/threads/{id}/history` API 做时间旅行——可以查看每次节点执行前后的状态快照。HITL 审批恢复也依赖 Checkpoint——interrupt 时状态被保存，resume 时从 checkpoint 恢复继续执行。"

### Q6: 多模型路由的策略是什么？

> "按角色分配：Planner 和 Reporter 用高能力模型（DeepSeek-Chat），Investigator 用中等模型，Critic 用低成本模型。主模型连续失败 3 次自动标记不可用，60 秒冷却后重试。每次调用记录 Token 用量和成本，提供 `/admin/usage` 查询接口。"

### Q7: v4.1 的处置回滚是怎么实现的？

> "6 个处置工具每个在执行前自动备份：kill_process 存进程信息 JSON，quarantine_file 存文件 SHA256 + 原始路径，block_ip 存防火墙规则名，remove_startup 导出 .reg 或 .xml 备份，repair_registry 导出 .reg。rollback_action 读备份文件执行逆操作——导入 .reg、删除防火墙规则、恢复文件等。所有备份存在 workspace/forensics_backups/，每条记录包含 action_id + timestamp + 操作详情。"

### Q8: 非管理员环境下取证工具怎么处理？

> "这是实际踩过的坑。Get-NetTCPConnection 需要管理员权限，非管理员直接卡死；Get-Process -IncludeUserName 也类似。我做了自动回退：网络检查主路径用 netstat -ano（无需管理员，0.3 秒完成），进程扫描去掉了 -IncludeUserName 改用基础 Get-Process。目前 8 个取证工具中 5 个完全不需要管理员，3 个部分受限但有友好提示。"

### Q9: 评估体系怎么设计的？

> "10 个指标，按难度（easy/medium/hard）和类别（日志分析/漏洞调查/攻击溯源/威胁情报/合规检查）分组。包含对抗样本（误导信息、不完整日志、矛盾数据）测试 Agent 鲁棒性。每次重大改动跑回归，自动生成对比报告。"

### Q10: 这套系统怎么进一步扩展？

> 1. **接知识图谱**：用 Neo4j 存资产-漏洞-攻击关系，Agent 走图查询做路径推理
> 2. **真沙箱**：把 `run_python` 换成 Docker/nsjail，支持多语言
> 3. **Prompt 版本管理**：引入 Prompt Registry + A/B 测试
> 4. **多平台取证**：支持 Linux/macOS 的 OSQuery 集成
> 5. **多模态**：支持 PDF/图片输入的安全报告分析

---

## 📊 可量化数据点（跑过 eval 后填上具体数字）

执行 `python -m eval.run_eval` 后，可写入简历的真实数字：

- 任务成功率（v2 baseline vs v4 对比）
- 任务平均完成时间
- Critic 评分均值
- 重复任务通过记忆复用的迭代轮数下降比例
- 关键词覆盖率提升幅度
- 幻觉率
- 模型 Fallback 触发频率
- 单任务平均成本（USD）
