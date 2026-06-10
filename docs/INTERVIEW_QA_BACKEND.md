# DeepInvestigate v4.1 — 后端面试官视角拷打问题集

> 模拟后端面试官，考察 Python/FastAPI/异步/数据库/系统设计等后端硬技能。
> 岗位方向：智能体开发 / AI 应用开发 / 大模型应用开发
> 难度：🟢 基础 | 🟡 进阶 | 🔴 深度 | ⚫ 压力

---

## 一、Python 语言基础

### 🟢 Q1: 你的项目里用了 `from __future__ import annotations`，这是干什么的？不加会怎样？

> **面试官意图**：考察 Python 基础，前向引用问题。

**回答**：
`from __future__ import annotations` 让所有类型注解变为**延迟求值**——注解被当作字符串存储，不在定义时解析。

不加的话，当你在类的方法中使用本类的类型注解时（比如 `def foo() -> MyClass`），因为 `MyClass` 还没定义完，会抛 `NameError`。加了之后注解变成字符串 `"MyClass"`，运行时才解析，避免了这个问题。

Python 3.11+ 可以用 `Self` 类型或 `typing.TYPE_CHECKING` 解决，但 `from __future__ import annotations` 是最简洁的方式，且是 PEP 563 的标准做法。

---

### 🟡 Q2: 你的 `@lru_cache(maxsize=4)` 用在 `get_planner_llm` 上，如果配置热更新了（比如改了 temperature），缓存会刷新吗？怎么解决？

> **面试官意图**：考察对缓存副作用的理解。

**回答**：
不会刷新。`lru_cache` 是纯内存缓存，基于函数参数做 key，不知道外部配置变了。

解决方案：
1. **简单方案**：提供 `get_planner_llm.cache_clear()` 手动清缓存，配置热更新时调用
2. **更好方案**：不用 `lru_cache`，改用带 TTL 的缓存（如 `cachetools.TTLCache`），过期自动刷新
3. **生产方案**：用 Redis 做配置中心，LLM 实例创建时实时读配置，不缓存实例本身

当前用 `lru_cache` 是因为个人项目配置不会热更新，够用。但面试中要能说出局限。

---

### 🟡 Q3: `ContextVar` 在你的项目里怎么用的？为什么不用全局变量传 `thread_id`？

> **面试官意图**：考察对 Python 异步编程中上下文传递的理解。

**回答**：
`ContextVar` 是 Python 3.7+ 引入的协程本地存储，类似 `threading.local` 但适用于 asyncio。

我的用法：
```python
_ctx: ContextVar[Optional[ToolContext]] = ContextVar("tool_context", default=None)

def set_context(ctx: ToolContext):
    _ctx.set(ctx)

def get_context() -> ToolContext:
    return _ctx.get()
```

为什么不用全局变量：
- FastAPI 是异步的，多个请求共享同一个事件循环线程
- 全局变量会被后续请求覆盖，导致 A 用户的 `thread_id` 串到 B 用户的工具调用里
- `ContextVar` 自动随 asyncio Task 传播，每个请求独立

这是 Python 异步编程的基本功，面试官会默认你应该知道。

---

### 🔴 Q4: `asyncio.Semaphore` 在你的评估系统里怎么用的？如果并发数是 3，第 4 个任务来了会发生什么？

> **面试官意图**：考察对 asyncio 并发控制的理解。

**回答**：
```python
sem = asyncio.Semaphore(concurrency)

async def guarded(t):
    async with sem:
        return await run_one(t)
```

第 4 个任务调用 `async with sem` 时，因为信号量已耗尽（3 个槽全被占），协程会**挂起（suspend）**，让出事件循环。等前面任意一个任务完成、释放信号量后，事件循环自动唤醒第 4 个任务继续执行。

关键点：
- 挂起不是阻塞，事件循环可以处理其他协程（如心跳、健康检查）
- 如果所有任务都卡在 `await` 上（如等 API 响应），3 个槽全占但 CPU 空闲，这是正常的
- 如果任务内部有 CPU 密集操作，会阻塞事件循环，需要 `run_in_executor` 抛到线程池

---

## 二、FastAPI 与 Web 框架

### 🟢 Q5: 你的流式接口用 `StreamingResponse`，和普通 `JSONResponse` 有什么区别？前端怎么知道流结束了？

> **面试官意图**：考察对 HTTP 流式响应的理解。

**回答**：
- `JSONResponse`：后端一次性构造完整 JSON，设 `Content-Length`，前端 `fetch().json()` 拿到完整数据
- `StreamingResponse`：后端用 `async generator` 逐块 `yield`，HTTP 用 `Transfer-Encoding: chunked`，前端用 `ReadableStream` 逐块读取

前端判断结束：
1. SSE 协议：最后一块是 `data: [DONE]\n\n`，前端检测到就关闭连接
2. HTTP 层：后端 generator 结束 → FastAPI 关闭响应体 → 前端 `reader.read()` 返回 `done: true`

我的实现两种都支持——SSE 的 `[DONE]` 是 OpenAI 协议约定，HTTP 的流结束是传输层保证。

---

### 🟡 Q6: 你的 `/chat/completions` 接口同时支持流式和非流式，代码里怎么处理的？为什么要保留非流式？

> **面试官意图**：考察 API 设计思维。

**回答**：
通过 `request.stream` 字段分支：
- `stream=True`：返回 `StreamingResponse`，用 `async generator` 逐块 SSE
- `stream=False`：调用 `run_agent_sync` 一次性跑完，返回 `JSONResponse`

保留非流式的原因：
1. **调试方便**：curl/Postman 直接看完整 JSON，不用拼 SSE 片段
2. **批量评估**：评估脚本用非流式，`await` 等结果，代码简洁
3. **兼容性**：有些 HTTP 客户端不支持 SSE（如某些老版本 axios），非流式兜底

---

### 🟡 Q7: 你的 `chat_api_v2.py` 里 `_get_input_guard()` 用了懒加载模式（`global _input_guard` + `is None` 检查），为什么不用 FastAPI 的 `@app.on_event("startup")` 初始化？

> **面试官意图**：考察对 FastAPI 生命周期的理解。

**回答**：
两种方式各有优劣：

懒加载（当前）：
- 优点：模块导入时不触发，只在第一次请求时初始化，启动快；Guardrails 不可用时静默降级，不影响其他路由
- 缺点：第一个请求会慢一点（冷启动）；全局变量不够优雅

`@app.on_event("startup")`：
- 优点：启动时预加载，第一个请求零延迟；集中管理所有初始化逻辑
- 缺点：Guardrails 初始化失败会导致整个应用启动失败

选懒加载是因为 Guardrails 是可选模块——如果没装 `mcp` 包或 Redis 没启动，不应该影响核心聊天功能。这是**优雅降级**的设计选择。

---

### 🔴 Q8: 你的 SSE 适配器里 `yield _chunk(...)` 是同步的，但外层是 `async def`，这有问题吗？

> **面试官意图**：考察对 Python 异步生成器的理解。

**回答**：
没有问题。`async def` 生成器里可以 `yield` 同步值，不需要 `await`。

`yield` 的行为：
- `yield value`：将 value 交给调用方的 `async for` 循环，协程挂起
- 调用方拿到 value 后，下次迭代时协程恢复，继续执行

`_chunk()` 是纯 CPU 操作（json.dumps + 字符串拼接），不需要 IO，同步执行即可。

v4.1 的 SSE 适配器还加了 `final_answer` 补偿机制——如果流式过程中没有 token 输出（比如 chat_responder 节点用非流式 LLM 调用），则在流结束前从 `on_chain_end` 事件中提取 `final_answer` 整体补发，确保前端始终有内容渲染。

面试官可能追问"如果 json.dumps 的数据很大（比如 100MB 的工具输出），会阻塞事件循环吗？"——会，这时应该用 `await asyncio.to_thread(json.dumps, data)` 抛到线程池。

---

## 三、异步与并发

### 🟡 Q9: 你的 `run_agent_sync` 函数名叫 "sync" 但里面用了 `await`，它到底是同步还是异步？

> **面试官意图**：考察命名规范和异步理解。

**回答**：
命名确实有歧义。"sync" 在这里的意思是"非流式"（non-streaming），即一次性跑完返回完整结果，而不是流式逐块返回。它本身是 `async def`，内部全是 `await`。

更好的命名应该是 `run_agent_non_streaming` 或 `run_agent_batch`。这是历史遗留命名，面试中主动承认命名不准确比狡辩好。

---

### 🔴 Q10: 你的 `tool_executor` 是 LangGraph 的 `ToolNode`，工具调用是同步还是异步？如果 3 个工具同时被调用，是并行还是串行？

> **面试官意图**：考察对 LangGraph 执行模型的理解。

**回答**：
LangGraph 的 `ToolNode` 默认**串行**执行工具——遍历 `tool_calls` 列表，逐个调用 `tool.ainvoke()`。

如果 Agent 一次返回 3 个 `tool_calls`，ToolNode 会：
1. 调工具 A，等结果
2. 调工具 B，等结果
3. 调工具 C，等结果

要并行执行，需要自定义 ToolNode：
```python
async def parallel_tool_node(state):
    tool_calls = state["messages"][-1].tool_calls
    tasks = [tool.ainvoke(tc) for tc, tool in zip(tool_calls, tools)]
    results = await asyncio.gather(*tasks)
    return {"messages": results}
```

当前串行是因为安全调查任务中工具间常有依赖（先查进程再查网络），并行意义不大。但如果做多数据源并发查询，并行能显著降低延迟。

---

### 🔴 Q11: 你的 v4.0 取证工具调用 PowerShell 是同步还是异步的？为什么用 `subprocess.run` 而不是 `asyncio.create_subprocess_exec`？

> **面试官意图**：考察对 IO 模型的理解和工程权衡。

**回答**：
当前 `_run_powershell_sync` 使用 `subprocess.run`，这是同步阻塞调用。原因：

1. **LangGraph 的 ToolNode 在线程池中执行同步 tool**——所以即使是同步 subprocess，也不会阻塞事件循环
2. `subprocess.run` 的超时机制更简单可靠——`timeout=N` 参数直接生效
3. Windows 上 `asyncio.create_subprocess_exec` 的 ProactorEventLoop 在某些 PowerShell 命令上有兼容性问题

但我保留了 `_run_powershell_async` 函数——用 `loop.run_in_executor` 把同步 subprocess 抛到线程池。这样既保持了代码简洁，又不阻塞事件循环。

如果面试官追问"线程池满了怎么办"——当前默认线程池大小足够（通常 40+），23 个工具的调用频率远达不到上限。如果真的高并发，可以换 `ProcessPoolExecutor` 或异步 subprocess。

---

## 四、数据库与存储

### 🟡 Q12: 你的四层记忆全用 Redis Stack，为什么不用 MySQL/PostgreSQL？Redis 挂了数据全丢怎么办？

> **面试官意图**：考察存储选型的 trade-off 理解。

**回答**：
选 Redis Stack 的原因：
1. **多数据结构**：String（工作记忆）、JSON（用户画像）、HNSW 向量索引（情景/程序记忆），一个服务全搞定
2. **低延迟**：毫秒级响应，Agent 每次推理前都要查记忆，延迟敏感
3. **运维简单**：一个 Docker 容器，不需要主从、分表

数据丢失风险：
- Redis 默认 RDB 快照 + AOF 日志，重启后可恢复
- 但 Redis 不是强持久化的——AOF 每秒 fsync 一次，最多丢 1 秒数据
- 对于记忆场景，丢 1 秒数据可接受（最多丢一条记忆，下次对话会重新生成）

如果面试官追问"用户画像丢了怎么办"——用户画像是低频更新的，可以从历史对话中重建。真正不能丢的数据（如付费记录）应该放 PostgreSQL。

---

### 🟡 Q13: ChromaDB 和 Redis HNSW 都在做向量检索，为什么用两个？不能统一吗？

> **面试官意图**：考察对向量库选型的理解。

**回答**：
两个向量库服务于不同场景：

| 维度 | ChromaDB（知识库） | Redis HNSW（记忆） |
|---|---|---|
| 数据量 | 大（万级文档） | 小（百级记忆） |
| 更新频率 | 低（周级灌库） | 高（每次对话） |
| 查询模式 | 语义检索 + 元数据过滤 | 纯 KNN |
| 持久化 | 需要（知识不能丢） | 可容忍丢失 |

统一到一个库技术上可行，但：
- ChromaDB 做高频写入性能不如 Redis
- Redis 存万级文档内存成本高
- **关注点分离**：知识库挂了不影响记忆，记忆挂了不影响知识库

---

### 🔴 Q14: 你的 `SqliteSaver` 存 checkpoint，SQLite 在并发写入时有什么问题？LangGraph 怎么解决的？

> **面试官意图**：考察对 SQLite 并发模型的理解。

**回答**：
SQLite 默认是**串行写**——同一时间只有一个连接能写入，其他写操作会等锁或返回 `SQLITE_BUSY`。

LangGraph 的 `AsyncSqliteSaver` 处理方式：
1. 使用 WAL 模式（Write-Ahead Logging），读写不互斥——读不阻塞写，写不阻塞读
2. 设置 `timeout` 参数，写锁等待超时后重试而非直接报错
3. 每个 `thread_id` 独立一行，不同会话的 checkpoint 写入不冲突

但同一 `thread_id` 的并发写入（比如两个请求同时操作同一会话）仍可能冲突。LangGraph 的设计假设是：同一 `thread_id` 的操作是串行的（前端不会同时发两个请求），所以实际不会遇到这个问题。

---

## 五、系统设计

### 🟡 Q15: 你的系统从用户发消息到第一个 token 返回，经历了哪些步骤？哪个步骤最慢？

> **面试官意图**：考察对系统全链路的理解。

**回答**：
链路：
1. FastAPI 接收请求，Pydantic 校验（<1ms）
2. Input Guard 正则检查（<1ms）
3. 闲聊检测（`_is_chat_question`）→ 如果是问候语直接走 chat_responder 快捷路由
4. 创建/恢复 Checkpoint（SQLite 读，~5ms）
5. `retrieve_memory` 节点：Redis 向量检索 + LLM 凝练（~200ms）
6. `retrieve_knowledge` 节点：ChromaDB 检索（~50ms）
7. `planner` 节点：LLM 生成计划（~500ms-2s）
8. `investigator` 节点：第一个 LLM token（~500ms-1s）
9. 工具调用（取证工具 PowerShell 执行 ~0.3-3s 不等）

**最慢的是 LLM 调用**，占端到端延迟的 80%+。其次是非管理员下的取证工具（PowerShell 子进程启动有开销）。

优化方向：
- 流式输出（已做）：不等完整响应，边生成边推
- 闲聊快捷路由（已做）：问候语跳过完整流水线
- 计划缓存：相似问题复用历史计划，跳过 Planner

---

### 🔴 Q16: 如果 DeepSeek API 完全挂了（不是慢，是 100% 失败），你的系统会怎样？怎么做到用户无感？

> **面试官意图**：考察容灾设计。

**回答**：
当前行为：
- ModelRouter 检测到连续失败 → 标记 unhealthy → 尝试 fallback
- 如果 fallback 也没配或也挂了 → 抛出异常 → SSE 流里推 `[FATAL]` → 前端显示错误

用户无感需要：
1. **多 Provider**：DeepSeek 挂了自动切 OpenAI / 本地模型
2. **请求重试**：指数退避重试 3 次，可能只是临时抖动
3. **降级响应**：LLM 全挂时，返回"AI 服务暂时不可用，请稍后重试" + 建议用户查看历史报告
4. **健康检查**：定期 ping 各 Provider，提前切换

当前只做了第 1 步的基础版（配了 fallback 字段但没配实际模型），这是生产化的待办项。

---

### 🟡 Q17: 你的 `config.yaml` 里 API Key 是明文写的，提交到 GitHub 怎么办？

> **面试官意图**：考察安全意识和工程规范。

**回答**：
绝对不应该提交明文 Key。正确做法：
1. `.gitignore` 加 `config.yaml`（或至少敏感部分）
2. 提供 `config.yaml.example` 模板，Key 字段写 `"YOUR_API_KEY_HERE"`
3. 生产环境用环境变量：`os.getenv("DEEPSEEK_API_KEY")`
4. CI/CD 中 Key 从 GitHub Secrets / Vault 注入

当前项目是个人开发，图方便写了明文。面试中要主动说"个人项目偷懒了，团队开发会用环境变量 + .env + .gitignore"。

---

## 六、错误处理与调试

### 🟡 Q18: 你的 `sse_adapter.py` 里最外层有 `try/except Exception`，但如果 generator 内部抛了 `GeneratorExit` 或 `StopAsyncIteration`，能 catch 住吗？

> **面试官意图**：考察对 Python 异常体系的理解。

**回答**：
`except Exception` 能 catch 住 `StopAsyncIteration`（它继承自 `Exception`），但 catch 不住 `GeneratorExit`（它继承自 `BaseException` 而非 `Exception`）。

不过实际场景中：
- `GeneratorExit` 是客户端断开连接时 Python 内部抛的，不需要 catch——它本身就是"停止生成"的信号
- `StopAsyncIteration` 是迭代结束的正常信号，不应该作为异常处理

当前 `except Exception` 的意图是 catch 业务异常（LLM 调用失败、JSON 解析错误等），不干扰 Python 内部的控制流异常。这是正确的。

---

### 🟡 Q19: 你的 Agent 跑了一半挂了（比如服务器重启），用户还能恢复吗？恢复到什么程度？

> **面试官意图**：考察 Checkpointer 的恢复粒度。

**回答**：
能恢复，恢复到**最后一个成功的节点之后**。

LangGraph 的 checkpoint 是**节点级**的——每执行完一个节点就保存一次。如果 `investigator` 节点执行完、正要进 `tool_executor` 时挂了，恢复后从 `tool_executor` 继续。

恢复粒度取决于节点粒度：
- 如果 `investigator` 内部有 3 次 LLM 调用，挂了会重做整个 `investigator` 节点（包括已完成的 LLM 调用）
- 如果 `tool_executor` 有 3 个工具调用，挂了会重做整个 `tool_executor` 节点

HITL 审批恢复也依赖这个机制——interrupt 时状态被保存，resume 时从 checkpoint 恢复继续。

---

### 🟡 Q20: 你的 PowerShell 命令里有大括号 `{}`，和 Python `.format()` 的大括号冲突了，你怎么解决的？

> **面试官意图**：考察实际工程踩坑经验。

**回答**：
这是我实际踩过的一个坑。取证工具的 PowerShell 命令包含 `Where-Object {$_.State -eq 'Running'}` 这样的语法，大括号被 Python 的 `str.format()` 当作格式化占位符，导致 `KeyError` 崩溃。

我的 PS_TEMPLATE 原本是：
```python
full_cmd = PS_TEMPLATE.format(cmd=command)  # BUG: {} 被 format 吃掉
```

改成 `str.replace()`：
```python
full_cmd = PS_TEMPLATE.replace("{cmd}", command)  # 只替换 {cmd}，其他 {} 不动
```

这个 bug 让我意识到：**当拼接两种不同语法的字符串时，永远用最原始的替换方式**，不要用可能解析目标语法的工具。

---

## 七、性能与优化

### 🟡 Q21: 你的 RAG 检索每次对话都做，如果用户连续问 5 个相关问题，每次都重新 embedding + 检索，怎么优化？

> **面试官意图**：考察缓存和性能优化思维。

**回答**：
优化策略：
1. **查询缓存**：对用户 query 做 hash，相同 query 直接返回缓存结果（命中率取决于用户是否重复问）
2. **会话级知识缓存**：第一次检索后，把相关文档存在 state 中，后续问题先查缓存再决定是否重新检索
3. **增量检索**：如果新问题和上一个问题语义相似（cosine > 0.9），只检索新关键词，合并结果
4. **预加载**：Planner 规划出调查方向后，提前异步检索相关知识

当前没做这些优化，因为单次检索 50ms，5 次也就 250ms，对用户体验影响不大。但如果是 100 万条知识库 + 100ms 检索延迟，就需要了。

---

### 🔴 Q22: 你的 `messages` 列表会随着对话越来越长，LLM 的 context window 有限，你怎么处理？

> **面试官意图**：考察对 LLM 上下文管理的理解。

**回答**：
当前策略：
1. **角色隔离**：Planner 只看到用户问题，不看到工具输出的几千字日志
2. **迭代上限**：`max_iterations=15`，防止无限增长
3. **LangGraph 自动管理**：每个节点的 messages 是共享的，但 LLM 调用时可以指定取最近 N 条

更完善的策略：
1. **滑动窗口**：只保留最近 N 轮对话 + 系统消息
2. **摘要压缩**：当 messages 超过阈值，用 LLM 将历史对话压缩为摘要
3. **工具输出截断**：工具返回结果超过 2000 字符就截断 + 标注省略量（已实现）
4. **记忆外置**：重要信息存长期记忆，不占 context window

当前项目对话不会特别长（单次调查任务 5-10 轮），DeepSeek 的 64K context 完全够用。但面试中要能说出扩展方案。

---

## 八、测试与质量

### 🟢 Q23: 你的项目里有单元测试吗？怎么测试一个 LangGraph 节点？

> **面试官意图**：考察测试意识。

**回答**：
当前没有单元测试，只有评估体系的集成测试（端到端跑完整任务）。

如果要加单元测试：
```python
@pytest.mark.asyncio
async def test_planner_node():
    state = new_initial_state(user_query="分析 SSH 暴力破解日志")
    result = await planner_node(state)
    plan = result.get("plan")
    assert isinstance(plan, list)
    assert len(plan) >= 2
    assert all(isinstance(s, str) for s in plan)
```

LangGraph 节点的测试要点：
- Mock LLM 调用（否则测试慢且花钱）
- 验证 state 更新是否正确
- 验证条件路由的返回值

面试中主动承认"没写单元测试，只有集成测试"比假装有更好。

---

### 🟡 Q24: 你的评估脚本 `run_eval.py` 里 `asyncio.wait_for(run_one(task), timeout=300)`，如果超时了，Agent 内部正在执行的工具调用会怎样？

> **面试官意图**：考察对超时和资源清理的理解。

**回答**：
`asyncio.wait_for` 超时后会向协程注入 `asyncio.CancelledError`。但这里有个问题：

- 如果 Agent 正在 `await` LLM API 调用，`CancelledError` 会中断等待，协程被取消
- 但如果 Agent 正在执行同步的 PowerShell 子进程（取证工具），`CancelledError` 无法中断同步操作——子进程会继续运行直到自己结束

这是 Python asyncio 的经典陷阱：**同步阻塞操作无法被异步取消**。

解决方案：
- 取证工具用 `asyncio.create_subprocess_exec` 替代 `subprocess.run`，可以被取消
- 或设置子进程级别的超时（`subprocess.run(timeout=...)`，已实现）

---

## 九、压力测试

### ⚫ Q25: 你的项目里 `try/except ImportError` 到处都是，这是好的设计还是代码坏味道？

> **面试官意图**：考察对代码质量的判断力。

**回答**：
这是**有意为之的优雅降级**，但确实有改进空间。

为什么用：
- 项目有多个可选模块（MCP、Guardrails、ModelRouter、Mem0），不是所有环境都会装
- 用 `try/except ImportError` 让核心功能（聊天）不依赖可选模块
- 比 `pip install` 强制安装所有依赖更友好

改进方向：
- 用依赖注入替代 try/except：在启动时检查可用模块，注入一个 `NullGuard` / `NullRouter` 空实现
- 或用 `importlib.util.find_spec` 提前检测，避免运行时反复 try/except

当前写法在个人项目中可接受，但在生产代码中应该用更结构化的依赖管理。

---

### ⚫ Q26: 你的 `config_deepseek.py` 里 `_get` 函数自己实现了一套 YAML 配置读取，为什么不用 Pydantic Settings？

> **面试官意图**：考察对 Python 配置管理最佳实践的了解。

**回答**：
历史原因——项目从 v1 开始就是手写的 YAML 读取，一直沿用。

Pydantic Settings 的优势：
```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    api_key: str
    model_path: str = "deepseek-chat"
    temperature: float = 0.4

    class Config:
        yaml_file = "config.yaml"
```
- 类型校验 + 自动补全
- 环境变量自动覆盖 YAML
- 支持 `.env` 文件

如果重构，会用 Pydantic Settings。当前方案在个人项目中够用，但团队项目应该用标准方案。

---

### ⚫ Q27: 给你 30 秒，说出你项目中最大的三个技术债务。

> **面试官意图**：考察自我认知和工程成熟度。

**回答**：
1. **没有单元测试**：全靠集成测试和手工验证，改代码不敢放心改
2. **API Key 明文在配置文件里**：安全红线，生产环境必须改
3. **代码沙箱是软隔离**：正则黑名单可绕过，不是真沙箱

这三个是"面试官听了会点头"的诚实回答，比说"没有技术债务"可信得多。

---

## 附录：按后端考察维度分类

| 考察维度 | 问题编号 |
|---|---|
| Python 语言基础 | Q1, Q2, Q3, Q4 |
| FastAPI / Web | Q5, Q6, Q7, Q8 |
| 异步与并发 | Q9, Q10, Q11 |
| 数据库与存储 | Q12, Q13, Q14 |
| 系统设计 | Q15, Q16, Q17 |
| 错误处理与调试 | Q18, Q19, Q20 |
| 性能与优化 | Q21, Q22 |
| 测试与质量 | Q23, Q24 |
| 代码质量与工程规范 | Q25, Q26, Q27 |
