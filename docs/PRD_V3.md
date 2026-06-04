# DeepInvestigate v3.0 升级需求文档（PRD）

> 版本：v1.0  
> 日期：2026-06-04  
> 状态：待评审  
> 目标：将 v2.0 从"Demo 级全栈项目"升级为"生产级 Agent 系统"，补齐 Agent 深度、工程可靠性与前沿性短板。

---

## 1. 背景与动机

### 1.1 现状

v2.0 已完成 LangGraph 多 Agent 编排、9 工具 Function Calling、四层记忆、RAG、流式 SSE、自研评估体系，在**广度**上覆盖了 Agent 开发的核心环节。

### 1.2 问题

在以下维度存在明显短板，面试中会被深度追问：

| # | 短板 | 影响 |
|---|---|---|
| 1 | 无 MCP 集成 | 工具不可跨项目复用，不符合 2025 行业标准 |
| 2 | 无 Human-in-the-Loop | 危险操作无人工审批，不满足生产安全要求 |
| 3 | 无 Checkpointing | 会话无法断点续跑，无时间旅行调试能力 |
| 4 | 无 Self-Reflection | 报告质量无自检机制，无法自我纠错 |
| 5 | 单一模型 | 无模型路由、fallback、成本优化 |
| 6 | 无 Guardrails | 无内容安全过滤、PII 检测、输出校验 |
| 7 | 评估集太小 | 15 条说服力不足，无对抗样本 |
| 8 | 无 Agent 间协议 | 无 A2A 通信、协商/辩论机制 |

### 1.3 目标

将 DeepInvestigate 从"能跑通的 Demo"升级为"面试中能深度展开的生产级 Agent 系统"，每个短板都能在面试中讲出设计决策和实现细节。

---

## 2. 功能需求

### FR-1：MCP（Model Context Protocol）集成

**优先级**：P0（最高）  
**投入**：2-3 天

#### 2.1.1 需求描述

将现有 9 个工具封装为 MCP Server，同时实现 MCP Client 节点接入 LangGraph，使工具可被任何支持 MCP 的 Agent 框架复用。

#### 2.1.2 功能点

- **FR-1.1 MCP Server**
  - 将 `run_python`、`query_logs`、`search_cve`、`rag_search`、`recall_memory`、`web_search`、`read_file`、`write_file`、`list_files` 封装为 MCP Tool 资源
  - 支持 `stdio` 和 `SSE` 两种传输方式
  - 每个工具保留原有的安全策略（沙箱隔离、路径校验等）

- **FR-1.2 MCP Client 节点**
  - 在 LangGraph 中新增 `mcp_tool_executor` 节点，通过 MCP Client 调用远程 MCP Server
  - 支持同时连接多个 MCP Server（本地 + 远程）
  - 工具 Schema 自动发现与注册

- **FR-1.3 兼容模式**
  - 保留现有 `ToolNode` 直接调用方式
  - 通过配置开关在"直连模式"和"MCP 模式"之间切换
  - 默认使用直连模式（零性能损耗），MCP 模式按需启用

#### 2.1.3 验收标准

- [ ] 启动 MCP Server 后，可通过 MCP Inspector 查看所有工具 Schema
- [ ] MCP Client 节点可成功调用远程 MCP Server 的工具
- [ ] 直连模式与 MCP 模式切换后，Agent 行为一致
- [ ] 工具安全策略在 MCP 模式下仍然生效

---

### FR-2：Human-in-the-Loop（HITL）

**优先级**：P0  
**投入**：1 天

#### 2.2.1 需求描述

在危险工具调用前插入人工审批节点，利用 LangGraph 的 `interrupt` 机制实现暂停-审批-继续的交互流程。

#### 2.2.2 功能点

- **FR-2.1 危险工具分级**
  - Level 0（安全）：`rag_search`、`recall_memory`、`list_files`、`read_file` — 无需审批
  - Level 1（需审批）：`run_python`、`write_file`、`web_search` — 需人工确认
  - Level 2（高风险）：`query_logs`（写操作）、`search_cve`（外网请求）— 需人工确认 + 理由说明

- **FR-2.2 审批节点**
  - 在 `tool_executor` 前插入 `human_approval` 节点
  - 使用 `interrupt_before=["human_approval"]` 暂停图执行
  - 审批信息包含：工具名、参数摘要、风险等级、Agent 调用理由

- **FR-2.3 前端审批 UI**
  - 在聊天界面中渲染审批卡片（工具名 + 参数 + 风险等级）
  - 提供"批准"/"拒绝"/"批准本次会话所有同类操作"三个按钮
  - 审批结果通过 `Command(resume=...)` 回传 LangGraph

- **FR-2.4 配置化**
  - 风险等级可通过 `config.yaml` 配置
  - 支持全局关闭 HITL（开发/演示模式）

#### 2.2.3 验收标准

- [ ] 危险工具调用时，前端弹出审批卡片
- [ ] 批准后 Agent 继续执行，拒绝后 Agent 跳过该工具并告知用户
- [ ] "批准本次会话所有同类操作"后，后续同类工具不再审批
- [ ] 关闭 HITL 后，所有工具自动通过

---

### FR-3：Checkpointing 与对话持久化

**优先级**：P0  
**投入**：1 天

#### 3.3.1 需求描述

接入 LangGraph Checkpointer，实现会话断点续跑、状态回溯（时间旅行调试）和跨请求状态恢复。

#### 3.3.2 功能点

- **FR-3.1 SQLite Checkpointer**
  - 使用 `SqliteSaver` 持久化图状态
  - 每次图执行后自动保存 checkpoint
  - 支持通过 `thread_id` 恢复历史会话

- **FR-3.2 会话恢复 API**
  - `POST /chat/completions` 支持 `session_id` 参数，自动恢复历史状态
  - `GET /threads/{thread_id}/history` 返回该会话的所有 checkpoint 列表
  - `GET /threads/{thread_id}/state` 返回最新状态快照

- **FR-3.3 时间旅行调试**
  - 支持 `graph.get_state_history(config)` 查看状态演进
  - 支持从任意 checkpoint 重放（replay）

- **FR-3.4 存储管理**
  - 自动清理超过 7 天的 checkpoint 数据
  - 支持手动删除指定会话的所有 checkpoint

#### 3.3.3 验收标准

- [ ] 同一 `session_id` 的多次请求共享 Agent 状态
- [ ] 可通过 API 查看会话的状态历史
- [ ] 重启服务后，历史会话可恢复
- [ ] 过期 checkpoint 自动清理

---

### FR-4：Self-Reflection / Critic Agent

**优先级**：P1  
**投入**：2 天

#### 4.4.1 需求描述

在 Reporter 输出报告后，增加 Critic Agent 节点对报告质量进行自检。不合格则回退到 Investigator 补充调查，形成"调查→报告→审查→修正"的闭环。

#### 4.4.2 功能点

- **FR-4.1 Critic 节点**
  - 新增 `critic` 节点，独立 LLM 调用（温度 0.2，保证审查稳定性）
  - 审查维度：事实准确性、逻辑完整性、关键信息缺失、建议可行性
  - 输出结构化评分（1-5 分）+ 具体修改建议

- **FR-4.2 条件路由**
  - 评分 ≥ 4：通过，进入 `update_memory`
  - 评分 < 4：回退到 `investigator`，附带 Critic 的修改建议作为补充调查方向
  - 最多回退 2 次，超过则强制通过并标记"未经充分审查"

- **FR-4.3 Critic 可见性**
  - Critic 的审查过程和评分通过 SSE 流式输出到前端
  - 最终报告中附带 Critic 评分

#### 4.4.3 验收标准

- [ ] Critic 能识别报告中明显的事实错误或信息缺失
- [ ] 评分 < 4 时，Agent 自动回退补充调查
- [ ] 回退次数不超过 2 次
- [ ] Critic 审查过程在前端可见

---

### FR-5：多模型路由与成本追踪

**优先级**：P1  
**投入**：1-2 天

#### 5.5.1 需求描述

支持多模型提供商，实现基于任务复杂度的模型路由、失败自动 fallback，以及 Token 用量与成本追踪。

#### 5.5.2 功能点

- **FR-5.1 模型配置**
  - 支持 DeepSeek、OpenAI（GPT-4o/GPT-4o-mini）、Claude 等多提供商
  - 统一通过 `config.yaml` 配置各模型的 API Key、Base URL、速率限制

- **FR-5.2 模型路由策略**
  - Planner：使用高能力模型（DeepSeek / GPT-4o），温度 0.3
  - Investigator：使用中等模型（DeepSeek / GPT-4o），温度 0.4
  - Reporter：使用高能力模型（DeepSeek / GPT-4o），温度 0.5
  - Critic：使用低成本模型（DeepSeek / GPT-4o-mini），温度 0.2
  - 简单工具调用结果解析：使用低成本模型

- **FR-5.3 Fallback 机制**
  - 主模型不可用时自动切换备用模型
  - 速率限制触发时自动降级到低成本模型
  - Fallback 事件记录到日志

- **FR-5.4 成本追踪**
  - 每次 LLM 调用记录 Token 用量（prompt + completion）
  - 按模型单价计算成本
  - 提供 `GET /admin/usage?days=7` API 查询用量统计
  - 前端管理面板展示用量趋势图

#### 5.5.3 验收标准

- [ ] 可通过配置切换模型提供商
- [ ] 主模型不可用时自动 fallback
- [ ] 不同 Agent 节点可使用不同模型
- [ ] 管理面板可查看 Token 用量和成本

---

### FR-6：Guardrails 安全护栏

**优先级**：P1  
**投入**：1-2 天

#### 6.6.1 需求描述

在 LLM 输入/输出两端增加安全护栏，包括内容安全过滤、PII 检测脱敏、输出结构校验。

#### 6.6.2 功能点

- **FR-6.1 输入护栏**
  - 用户输入敏感词检测（政治、暴力、色情等）
  - 检测到敏感内容时拒绝处理，返回友好提示
  - 支持自定义敏感词列表

- **FR-6.2 输出护栏**
  - Reporter 输出内容安全扫描
  - PII 检测（身份证号、手机号、邮箱、IP 地址等），自动脱敏
  - 输出格式校验（确保报告包含必要章节）

- **FR-6.3 审计日志**
  - 所有护栏拦截事件记录到审计日志
  - 包含时间、用户、触发规则、原始内容摘要

#### 6.6.3 验收标准

- [ ] 输入含敏感词时被拦截
- [ ] 输出含 PII 时自动脱敏
- [ ] 拦截事件有完整审计记录
- [ ] 护栏规则可通过配置更新

---

### FR-7：评估体系升级

**优先级**：P1  
**投入**：1 天

#### 7.7.1 需求描述

将评估数据集从 15 条扩展到 50+ 条，增加对抗样本和跨领域任务，提升评估说服力。

#### 7.7.2 功能点

- **FR-7.1 数据集扩展**
  - 从 15 条扩展到 ≥ 50 条
  - 按难度分级：easy 15 / medium 20 / hard 15
  - 按类别覆盖：日志分析 / 漏洞调查 / 攻击溯源 / 威胁情报 / 合规检查

- **FR-7.2 对抗样本**
  - 加入 5+ 条对抗样本（含误导信息、不完整日志、矛盾数据）
  - 评估 Agent 在对抗场景下的鲁棒性

- **FR-7.3 新增指标**
  - Critic Score（Critic 评分均值）
  - Fallback Rate（模型 fallback 频率）
  - Guardrail Trigger Rate（护栏触发频率）
  - Cost per Task（单任务平均成本）

- **FR-7.4 基线对比**
  - 保留 v2.0 基线数据
  - v3.0 回归测试自动生成对比报告

#### 7.7.3 验收标准

- [ ] 数据集 ≥ 50 条，覆盖 5 个类别
- [ ] 包含 ≥ 5 条对抗样本
- [ ] 新增 4 项指标可正常计算
- [ ] v2 vs v3 对比报告自动生成

---

### FR-8：Agent 间通信协议（A2A）

**优先级**：P2  
**投入**：2 天

#### 8.8.1 需求描述

实现简单的 Agent-to-Agent 通信协议，支持 Planner 与 Investigator 之间通过结构化消息协商任务分配，支持多 Investigator 并行调查后结果汇总。

#### 8.8.2 功能点

- **FR-8.1 A2A 消息格式**
  - 定义标准 A2A 消息结构：`{from, to, type, payload, correlation_id}`
  - 消息类型：`task_assign`、`task_result`、`clarification_request`、`status_update`

- **FR-8.2 协商机制**
  - Investigator 可向 Planner 发送 `clarification_request` 请求任务澄清
  - Planner 可动态调整计划并重新分配

- **FR-8.3 并行调查**
  - 支持 Planner 将独立子任务分配给多个 Investigator 并行执行
  - Reporter 汇总多个 Investigator 的结果

#### 8.8.3 验收标准

- [ ] A2A 消息格式定义完整
- [ ] Investigator 可向 Planner 请求澄清
- [ ] 支持多 Investigator 并行调查
- [ ] 并行结果可正确汇总

---

## 3. 非功能需求

### NFR-1：兼容性

- 前端 API 协议不变，现有 Next.js 前端无需改动即可使用 v3.0
- 保留 v2.0 所有功能，新功能通过配置开关控制
- `config.yaml` 向后兼容，新增配置项有默认值

### NFR-2：性能

- 直连工具调用性能不退化（与 v2.0 持平）
- MCP 模式额外延迟 ≤ 50ms
- Checkpointing 写入不阻塞 Agent 主流程（异步写入）

### NFR-3：可测试性

- 每个新模块提供独立单元测试
- HITL 审批流程可通过 Mock 测试
- 评估体系可一键运行

### NFR-4：可观测性

- 所有新节点接入 LangSmith 追踪
- 关键操作记录结构化日志
- 护栏拦截、模型 fallback 等事件有专门日志通道

---

## 4. 约束与假设

### 约束

- 不引入新的基础设施依赖（继续使用 Docker Compose 管理 Redis + ChromaDB）
- 不修改前端核心交互流程
- Python 版本保持 3.12

### 假设

- 用户已有 DeepSeek API Key，可选配置 OpenAI / Claude API Key
- 本地开发环境可运行 Node.js（MCP Server 需要）
- 评估运行时有稳定的网络连接（调用外部 API）

---

## 5. 里程碑

| 阶段 | 内容 | 预计投入 |
|---|---|---|
| M1 | FR-1 MCP + FR-2 HITL + FR-3 Checkpointing | 4-5 天 |
| M2 | FR-4 Critic + FR-5 多模型路由 | 3-4 天 |
| M3 | FR-6 Guardrails + FR-7 评估升级 | 2-3 天 |
| M4 | FR-8 A2A + 整体联调 + 文档更新 | 2-3 天 |

**总计**：11-15 天

---

## 6. 风险

| 风险 | 影响 | 缓解措施 |
|---|---|---|
| MCP Python SDK 不稳定 | FR-1 延期 | 优先实现 stdio 传输，SSE 作为可选项 |
| LangGraph interrupt 与 SSE 流式冲突 | FR-2 复杂化 | 先做非流式 HITL，流式 HITL 作为 stretch goal |
| 多模型 API 兼容性差异 | FR-5 调试量大 | 统一封装为 OpenAI 兼容接口 |
| A2A 过度设计 | FR-8 投入过大 | 先做最小可用版本（消息传递 + 并行），不引入消息队列 |

---

## 7. 附录：与 v2.0 对比

| 维度 | v2.0 | v3.0 目标 |
|---|---|---|
| 工具复用 | 仅本项目可用 | MCP Server，跨项目复用 |
| 安全审批 | 无 | HITL 三级审批 |
| 会话持久化 | 无 | SQLite Checkpointer + 时间旅行 |
| 质量控制 | 无 | Critic Agent 自审查 |
| 模型管理 | 单一 DeepSeek | 多模型路由 + fallback + 成本追踪 |
| 安全护栏 | 仅代码沙箱 | 输入/输出护栏 + PII 脱敏 + 审计 |
| 评估规模 | 15 条 / 6 指标 | 50+ 条 / 10 指标 / 对抗样本 |
| Agent 通信 | 隐式（共享状态） | A2A 显式协议 + 并行调查 |
