# DeepInvestigate: 智能数据科学助手

## 项目简介

DeepInvestigate 是一个自主调查分析智能体，为用户提供专业级的数据洞察和报告。

## 快速开始

### 系统要求

- Python 3.10+
- Node.js 16+
- 推荐使用 conda 环境管理工具

### 安装步骤

1. **安装 Python 依赖**
   ```bash
   conda create -n DeepInvestigate python=3.12 -y
   conda activate DeepInvestigate
   pip install -r requirements.txt
   ```

2. **安装前端依赖**
   ```bash
   cd demo/chat/frontend
   npm install
   cd ../../..
   ```

3. **配置 API 密钥**
   - 编辑 `API/config.yaml` 文件，填写你的 DeepSeek API 密钥

### 运行服务

项目提供了便捷的启动和停止脚本，支持 Windows 和 Linux 系统：

#### Windows 系统

1. **启动所有服务**
   ```bash
   # 双击运行或在命令行执行
   start_all.bat
   ```

2. **停止所有服务**
   ```bash
   # 双击运行或在命令行执行
   stop_all.bat
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

## 使用方法

### 基本使用流程

1. **输入分析需求**：在聊天框中描述你想要完成的分析任务
2. **查看分析结果**：系统会自动处理数据并生成分析报告
3. **下载报告**：分析完成后，你可以下载生成的报告文件

