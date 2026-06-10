# DeepInvestigate v4.0 执行手册

> 从零搭建 -> 跑通测试 -> 加处置能力，完整操作指南。
>
> 适用场景：换到新电脑后，按本文档一步步执行即可。

---

## 目录

- [第一部分：环境搭建](#第一部分环境搭建)
- [第二部分：配置与启动](#第二部分配置与启动)
- [第三部分：运行端到端测试](#第三部分运行端到端测试)
- [第四部分：常见问题排查](#第四部分常见问题排查)
- [第五部分：处置能力设计方案](#第五部分处置能力设计方案)
- [附录：完整检查清单](#附录完整检查清单)

---

## 第一部分：环境搭建

### 1.1 前置条件

| 软件 | 版本要求 | 下载地址 |
|------|---------|---------|
| Python | 3.10 ~ 3.12 | https://www.python.org/downloads/ |
| Miniconda (推荐) | 最新版 | https://docs.conda.io/en/latest/miniconda.html |
| Docker Desktop | 最新版 | https://www.docker.com/products/docker-desktop/ |
| Node.js | 16+ | https://nodejs.org/ |
| Git | 任意版本 | https://git-scm.com/download/win |

### 1.2 克隆项目

```powershell
# 假设你已经把项目拷贝到了 U盘/网盘，解压到本地
# 或者从 Git 仓库克隆
git clone <你的仓库地址> deepinvestigate
cd deepinvestigate
```

### 1.3 创建 Python 虚拟环境

```powershell
# 方式一：conda（推荐）
conda create -n deepinvestigate python=3.12 -y
conda activate deepinvestigate

# 方式二：venv（如果没有 conda）
python -m venv venv
.\venv\Scripts\activate
```

### 1.4 安装依赖

```powershell
# 基础依赖
pip install -r requirements.txt

# v3.0/v4.0 扩展依赖
pip install -r requirements-v2.txt
```

> 如果安装失败，常见原因：
> - `sentence-transformers` 编译失败 -> 安装 Visual C++ Build Tools 或降级 `pip install sentence-transformers==2.7.0`
> - `chromadb` 版本冲突 -> 尝试 `pip install chromadb==0.5.23`
> - 网络问题 -> 使用清华镜像：`pip install -r requirements-v2.txt -i https://pypi.tuna.tsinghua.edu.cn/simple`

### 1.5 启动基础设施（Docker）

```powershell
# 确保 Docker Desktop 已启动（右下角托盘图标显示 running）
docker compose up -d

# 验证
docker ps
# 应该看到 deepinvestigate-redis 和 deepinvestigate-chroma 两个容器
```

### 1.6 安装前端依赖

```powershell
cd demo/chat/frontend
npm install
cd ../../..
```

---

## 第二部分：配置与启动

### 2.1 配置 API 密钥

编辑 `API/config.yaml`，填写你的 DeepSeek API 密钥：

```yaml
api:
  base: "https://api.deepseek.com/v1"
  model_path: "deepseek-chat"
  api_key: "sk-你的密钥"          # <--- 改这里

models:
  providers:
    deepseek:
      api_key: "sk-你的密钥"      # <--- 改这里
      base_url: "https://api.deepseek.com/v1"
```

DeepSeek API 密钥获取：https://platform.deepseek.com/api_keys （注册就送额度）

> 可选：Embedding 模型也用 DeepSeek 的话不需要改 embedder 配置。如果用 OpenAI Embedding，需要额外填写 `embedder.api_key`。

### 2.2 灌入知识库（首次必须）

```powershell
cd API
python -m rag.ingest --dir ../knowledge
cd ..
```

预期输出：
```
Ingesting files from ../knowledge...
Loaded XX documents into collection 'knowledge_base'
Done.
```

如果报 `ChromaDB connection refused`，检查 Docker 是否正常运行（`docker ps`）。

### 2.3 启动完整服务

```powershell
# Windows 一键启动
.\start_all_v2.bat
```

或手动分别启动：
```powershell
# 终端1：后端
cd API
python server_v2.py

# 终端2：前端
cd demo/chat/frontend
npm run dev
```

### 2.4 验证服务可用

浏览器访问：
- http://localhost:4000 — 前端聊天界面
- http://localhost:8201/docs — 后端 API 文档

在前端输入"你好"，如果收到回复说明服务正常。

---

## 第三部分：运行端到端测试

这是 v4.0 的核心验证步骤，确认 8 个取证工具都能正常工作。

### 3.1 普通模式测试（不需要管理员）

```powershell
# 确保在项目根目录，且 conda 环境已激活
cd API
python -m tools.forensics.test_forensics
```

**预期输出（核心部分）：**

```
============================================================
  DeepInvestigate v4.0 端到端测试
============================================================
  时间: 2026-06-05 16:30:00
  主机: DESKTOP-XXX
  管理员: 否

[1/6] 环境检查
  Python: 3.12.0
  Windows: 是
  PowerShell: 可用
  管理员: 否 (部分测试将跳过)

[2/6] 模块导入
  OK tools.forensics._utils
  OK tools.forensics.system_info
  OK tools.forensics.process_scanner
  ... (全部 11 个模块)

[3/6] 公共函数
  run_powershell: OK (0.5s)
  safe_json_parse: OK
  ...

[4/6] 取证工具真实调用
  collect_system_info: OK (2.1s)
  scan_processes: OK 进程=85, 可疑=2 (8.3s)
  check_network: OK 连接=32, 可疑=0 (3.1s)
  check_defender_logs: OK Defender=启用, 威胁=0 (2.5s)
  check_startup: OK 启动项=15, 可疑=0 (4.2s)
  check_file_integrity: OK 发现=5, 高危=0 (6.8s)
  audit_logins: 跳过 (需要管理员)
  scan_registry: OK 发现=8, 可疑=0 (3.5s)

[5/6] 风险评分引擎
  干净主机: OK 评分=0/正常
  感染主机: OK 评分=85.5/严重, 指标=5个
  关联加权: OK 关联加分=22.5

[6/6] 错误处理
  超时处理: OK
  空JSON处理: OK

[7] 完整调查流程模拟
  模拟: 用户请求 -> 规划 -> 采集 -> 分析 -> 评分 -> 报告
  完整流程通过

============================================================
  测试报告
============================================================
  通过: 28 / 失败: 0 / 总计: 28
  全部通过!
============================================================
```

### 3.2 管理员模式测试（完整）

```powershell
# 右键 PowerShell 图标 -> 以管理员身份运行
# 激活 conda 环境
conda activate deepinvestigate

cd API
python -m tools.forensics.test_forensics --admin
```

管理员模式额外测试：
- `audit_logins` — 读取 Windows 安全事件日志

### 3.3 测试未通过怎么办

跳到第四部分，按常见问题逐项排查。

---

## 第四部分：常见问题排查

### 问题1：`PowerShell 不可用`

```
原因：PowerShell 未安装或 PATH 未配置
解决：Windows 10/11 自带 PowerShell，检查是否能手动运行 `powershell` 命令
```

### 问题2：`collect_system_info 返回错误`

```
可能原因：
- Get-LocalUser 在 Windows Home 版不可用（正常，不影响核心功能）
- 杀软查询在非管理员下可能失败（正常）
- 忽略 `_errors` 字段中的非关键错误即可
```

### 问题3：`scan_processes` 耗时很长或返回少量进程

```
可能原因：
- PowerShell 执行策略限制 -> 运行：Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
- 签名验证对每个进程执行 PowerShell 子调用，耗时正常。120s 超时足够
- 如果卡住，检查是否有杀软拦截 PowerShell 子进程创建
```

### 问题4：`check_network` 返回 0 连接

```
可能原因：
- Get-NetTCPConnection 需要管理员权限才能看到其他进程的连接
- 非管理员下只能看到自己的连接 -> 正常现象
- 用管理员模式运行可获得完整结果
```

### 问题5：`audit_logins` 返回"权限不足"

```
这是预期行为。读取安全事件日志必须管理员权限。
以管理员身份运行 PowerShell 后再执行测试即可。
```

### 问题6：模块导入失败 `No module named 'xxx'`

```
解决：
1. 确认 conda 环境已激活：conda activate deepinvestigate
2. 确认在 API 目录下执行：cd API
3. 重新安装依赖：pip install -r requirements-v2.txt
4. 检查 Python 路径：where python
```

### 问题7：ChromaDB / Redis 连接失败

```
解决：
1. 确认 Docker Desktop 正在运行
2. 执行 docker compose up -d 启动容器
3. 执行 docker ps 查看容器状态
4. 如果容器一直 restarting，检查端口是否被占用：
   netstat -ano | findstr 6379
   netstat -ano | findstr 8000
```

### 问题8：风险评分引擎测试中关联加权为 0

```
检查 mock 数据中的 entity_id 是否匹配。
同一 PID 100 的进程同时出现在 scan_processes 和 check_network 中，
且 entity_id 都是 "100"，才会触发关联加权。
```

---

## 第五部分：处置能力设计方案

> **前置条件**：第三部分的测试全部通过后，再开始本部分。

### 5.1 设计原则

| 原则 | 说明 |
|------|------|
| **最高安全级别** | 所有处置工具 Risk Level 3，必须 HITL 审批 |
| **可回滚** | 每个操作前自动备份（文件隔离而非删除，注册表导出） |
| **白名单保护** | 系统关键进程/文件/注册表项禁止操作 |
| **操作审计** | 每次处置记录时间、操作、结果、回滚信息 |

### 5.2 新增工具清单

#### 工具 1：`kill_process` — 终止可疑进程

| 属性 | 值 |
|------|-----|
| **风险等级** | Level 3 |
| **输入** | `pid` (int): 进程 ID；`force` (bool, 默认 true): 强制终止 |
| **输出** | `{success, process_name, exit_code, backup_info}` |
| **实现** | `taskkill /PID {pid} /F` |
| **安全** | 系统进程白名单检查，PID > 4（System 进程禁止） |

#### 工具 2：`quarantine_file` — 隔离恶意文件

| 属性 | 值 |
|------|-----|
| **风险等级** | Level 3 |
| **输入** | `file_path` (str): 文件绝对路径 |
| **输出** | `{success, original_path, quarantine_path, sha256}` |
| **实现** | 计算 SHA256 -> 移动到 `workspace/quarantine/` -> 原位置写入空文件占位 |
| **安全** | 系统目录白名单（C:\Windows\System32\*.dll 等禁止操作） |

#### 工具 3：`block_ip` — 防火墙封禁 IP

| 属性 | 值 |
|------|-----|
| **风险等级** | Level 3 |
| **输入** | `ip` (str): 要封禁的 IP；`direction` (默认 "outbound"): inbound/outbound/both |
| **输出** | `{success, rule_name, ip, direction}` |
| **实现** | `netsh advfirewall firewall add rule name="DeepInvestigate_Block_{ip}" dir=out remoteip={ip} action=block` |
| **安全** | 内网 IP 白名单（192.168./10./172.16. 默认不封禁） |

#### 工具 4：`remove_startup` — 删除恶意启动项

| 属性 | 值 |
|------|-----|
| **风险等级** | Level 3 |
| **输入** | `source` (str): "registry" / "task" / "service"；`identifier` (str): 注册表键名/任务名/服务名 |
| **输出** | `{success, type, identifier, backup}` |
| **实现** | 注册表：导出备份 -> Remove-ItemProperty；任务：导出XML -> Unregister-ScheduledTask；服务：导出配置 -> Stop+Disable |
| **安全** | 系统服务白名单 |

#### 工具 5：`repair_registry` — 修复注册表

| 属性 | 值 |
|------|-----|
| **风险等级** | Level 3 |
| **输入** | `path` (str): 注册表路径；`key` (str): 键名；`action` (str): "delete" / "restore" (恢复默认值) |
| **输出** | `{success, path, key, action, backup}` |
| **实现** | 导出备份 -> Remove-ItemProperty / Set-ItemProperty |
| **安全** | 系统关键路径白名单 |

#### 工具 6：`rollback_action` — 回滚处置操作

| 属性 | 值 |
|------|-----|
| **风险等级** | Level 2 |
| **输入** | `action_id` (str): 之前处置操作返回的 ID |
| **输出** | `{success, action_id, restored_items}` |
| **实现** | 从备份恢复文件/注册表/防火墙规则/服务配置 |
| **安全** | 仅能回滚本系统执行的操作 |

### 5.3 HITL 审批更新

在 `API/agent/graph.py` 中新增：

```python
TOOL_RISK_LEVELS = {
    # ... 原有 ...
    # v4.1 处置工具 (全部 Level 3)
    "kill_process":      3,
    "quarantine_file":   3,
    "block_ip":          3,
    "remove_startup":    3,
    "repair_registry":   3,
    "rollback_action":   2,
}
```

Level 3 工具的行为：
- **强制审批**：每次调用都必须用户确认，不支持"本次会话信任"
- **显示详细信息**：操作目标、影响范围、风险提示
- **审批 UI 新增"回滚"按钮**：处置完成后，前端显示"撤销此操作"

### 5.4 安全白名单配置

在 `API/config.yaml` 中新增：

```yaml
forensics:
  # ... 原有配置 ...

  # v4.1 处置安全白名单
  remediation:
    # 系统进程保护（绝对不可终止）
    protected_processes:
      - "System"
      - "System Idle Process"
      - "svchost.exe"
      - "lsass.exe"
      - "csrss.exe"
      - "smss.exe"
      - "winlogon.exe"
      - "services.exe"
      - "wininit.exe"
      - "dwm.exe"
      - "explorer.exe"
      - "csrss.exe"

    # 系统文件保护（绝对不可操作）
    protected_paths:
      - "C:\\Windows\\System32\\"
      - "C:\\Windows\\SysWOW64\\"
      - "C:\\Windows\\Boot\\"
      - "C:\\Windows\\WinSxS\\"
      - "C:\\Program Files\\Windows Defender\\"

    # 内网 IP 保护（默认不封禁）
    protected_networks:
      - "127.0.0.0/8"
      - "10.0.0.0/8"
      - "172.16.0.0/12"
      - "192.168.0.0/16"

    # 备份目录
    backup_dir: "workspace/forensics_backups"
    # 备份保留天数
    backup_retention_days: 30
```

### 5.5 Reporter 更新

报告模板新增"处置结果"章节：

```markdown
## 9. 处置结果

| 操作 | 目标 | 结果 | 回滚ID |
|------|------|------|--------|
| 终止进程 | PID 2844 update.exe | 成功 | rollback_001 |
| 隔离文件 | C:\Temp\update.exe | 成功 | rollback_002 |
| 封禁IP | 45.33.32.156 | 成功 | rollback_003 |
| 删除启动项 | HKCU Run: WindowsUpdate | 成功 | rollback_004 |
```

### 5.6 Critic 更新

新增审查维度：

```
6. **处置安全性** (v4.1)：处置操作是否在安全白名单内？有无误杀风险？
7. **处置完整性**：是否覆盖了所有发现的威胁指标？有无遗漏？
```

### 5.7 文件清单

```
API/tools/forensics/
├── ... (原有 8 个取证工具) ...
├── remediation/              # ★ NEW
│   ├── __init__.py
│   ├── kill_process.py       # 进程终止
│   ├── quarantine_file.py    # 文件隔离
│   ├── block_ip.py           # IP 封禁
│   ├── remove_startup.py     # 启动项清理
│   ├── repair_registry.py    # 注册表修复
│   └── rollback.py           # 操作回滚
└── test_forensics.py         # ★ 更新：新增处置工具测试
```

### 5.8 实施步骤

| 步骤 | 内容 | 估时 |
|------|------|------|
| 1 | 创建 `tools/forensics/remediation/` 目录 | 5分钟 |
| 2 | 实现 `kill_process` | 30分钟 |
| 3 | 实现 `quarantine_file` | 30分钟 |
| 4 | 实现 `block_ip` | 30分钟 |
| 5 | 实现 `remove_startup` | 40分钟 |
| 6 | 实现 `repair_registry` | 30分钟 |
| 7 | 实现 `rollback_action` | 40分钟 |
| 8 | 更新 `registry.py` 注册新工具 | 10分钟 |
| 9 | 更新 `graph.py` TOOL_RISK_LEVELS + HITL Level 3 | 20分钟 |
| 10 | 更新 `config.yaml` 安全白名单 | 15分钟 |
| 11 | 更新 `prompts.py` Investigator/Reporter/Critic | 30分钟 |
| 12 | 更新 `test_forensics.py` 处置工具测试 | 40分钟 |
| 13 | 端到端测试验证 | 30分钟 |
| **总计** | | **约 6 小时（一个下午）** |

---

## 附录：完整检查清单

### 环境搭建

- [ ] Python 3.10+ 已安装，`python --version` 正常
- [ ] conda 或 venv 环境已创建并激活
- [ ] `requirements.txt` + `requirements-v2.txt` 依赖全部安装成功
- [ ] Docker Desktop 已安装并启动
- [ ] `docker compose up -d` 成功启动 Redis + ChromaDB
- [ ] Node.js 16+ 已安装，`npm install` 成功
- [ ] `API/config.yaml` 中已填写 DeepSeek API 密钥
- [ ] 知识库已灌入：`python -m rag.ingest --dir ../knowledge`
- [ ] 服务启动正常，前端 http://localhost:4000 可访问

### 取证工具验证

- [ ] `collect_system_info` — 返回系统信息 JSON
- [ ] `scan_processes` — 返回进程列表 + 可疑标记
- [ ] `check_network` — 返回网络连接列表 + 可疑标记
- [ ] `check_defender_logs` — 返回 Defender 状态和告警
- [ ] `check_startup` — 返回启动项/任务/服务列表
- [ ] `check_file_integrity` — 返回可疑文件列表
- [ ] `audit_logins` — 返回登录事件（需管理员）
- [ ] `scan_registry` — 返回注册表可疑项
- [ ] 风险评分引擎 — 干净主机 0 分，感染主机 > 40 分
- [ ] 关联加权 — 同一实体多项指标触发额外加分
- [ ] 完整调查流程模拟通过

### 处置工具（跑通测试后执行）

- [ ] `kill_process` 实现并测试
- [ ] `quarantine_file` 实现并测试
- [ ] `block_ip` 实现并测试
- [ ] `remove_startup` 实现并测试
- [ ] `repair_registry` 实现并测试
- [ ] `rollback_action` 实现并测试
- [ ] HITL Level 3 审批流程正常
- [ ] 安全白名单防护生效
- [ ] 完整调查+处置流程端到端通过