"""
Configuration module for DeepSeek API Server
Contains all configuration constants and environment setup
"""

import os
import yaml

# Environment setup
os.environ.setdefault("MPLBACKEND", "Agg")

# Load configuration from YAML file
current_dir = os.path.dirname(os.path.abspath(__file__))
config_path = os.path.join(current_dir, "config.yaml")

with open(config_path, 'r', encoding='utf-8') as f:
    config = yaml.safe_load(f)

# API Configuration
# DeepSeek API endpoint
API_BASE = config['api']['base']
MODEL_PATH = config['api']['model_path']
# DeepSeek API Key
API_KEY = config['api']['api_key']

# Workspace configuration
WORKSPACE_BASE_DIR = "workspace_deepseek"
HTTP_SERVER_PORT = 8101  # 使用不同的端口避免冲突
# 注意：0.0.0.0仅用于服务器绑定，客户端访问需要使用实际的IP地址
HTTP_SERVER_BASE = f"http://localhost:{HTTP_SERVER_PORT}"

# API Server Configuration
API_HOST = "0.0.0.0"
API_PORT = 8201  # 使用不同的端口避免冲突
API_TITLE = "DeepAnalyze DeepSeek API"
API_VERSION = "1.0.0"

# Thread cleanup configuration
CLEANUP_TIMEOUT_HOURS = 12
CLEANUP_INTERVAL_MINUTES = 30

# Code execution configuration
CODE_EXECUTION_TIMEOUT = 120
MAX_NEW_TOKENS = 8192

# File handling configuration
FILE_STORAGE_DIR = os.path.join(WORKSPACE_BASE_DIR, "_files")
VALID_FILE_PURPOSES = ["fine-tune", "answers", "file-extract", "assistants"]

# Model configuration
DEFAULT_TEMPERATURE = 0.4
DEFAULT_MODEL = "deepseek-chat"

# Supported tools
SUPPORTED_TOOLS = ["code_interpreter"]

# ============================================================
# DeepInvestigate v2.0 新增配置加载
# ============================================================

def _get(section: str, key: str, default=None):
    """安全读取嵌套配置项"""
    try:
        return config.get(section, {}).get(key, default)
    except Exception:
        return default


# Redis 配置
REDIS_HOST = _get("redis", "host", "localhost")
REDIS_PORT = _get("redis", "port", 6379)
REDIS_DB = _get("redis", "db", 0)
REDIS_PASSWORD = _get("redis", "password", "") or None
WORKING_MEMORY_TTL = _get("redis", "working_memory_ttl", 1800)
EPISODIC_INDEX = _get("redis", "episodic_index", "em_idx")

# ChromaDB 配置
CHROMA_HOST = _get("chroma", "host", "localhost")
CHROMA_PORT = _get("chroma", "port", 8000)
CHROMA_COLLECTION = _get("chroma", "collection", "knowledge_base")
CHROMA_DEFAULT_TOP_K = _get("chroma", "default_top_k", 5)

# Embedding 配置
EMBEDDER_PROVIDER = _get("embedder", "provider", "huggingface")
EMBEDDER_MODEL = _get("embedder", "model", "BAAI/bge-m3")
EMBEDDER_DEVICE = _get("embedder", "device", "cpu")
EMBEDDER_DIM = _get("embedder", "dim", 1024)
EMBEDDER_BATCH_SIZE = _get("embedder", "batch_size", 32)
# 仅 openai provider 使用（独立于 LLM 的 api_base/api_key）
EMBEDDER_API_BASE = _get("embedder", "api_base", "") or API_BASE
EMBEDDER_API_KEY = _get("embedder", "api_key", "") or API_KEY

# LangSmith 配置
LANGSMITH_ENABLED = _get("langsmith", "enabled", False)
LANGSMITH_PROJECT = _get("langsmith", "project", "DeepInvestigate-Dev")
LANGSMITH_API_KEY = _get("langsmith", "api_key", "")
LANGSMITH_ENDPOINT = _get("langsmith", "endpoint", "https://api.smith.langchain.com")

# Agent 配置
AGENT_MAX_ITERATIONS = _get("agent", "max_iterations", 15)
AGENT_RECURSION_LIMIT = _get("agent", "recursion_limit", 25)
PLANNER_TEMPERATURE = _get("agent", "planner_temperature", 0.3)
INVESTIGATOR_TEMPERATURE = _get("agent", "investigator_temperature", 0.4)
REPORTER_TEMPERATURE = _get("agent", "reporter_temperature", 0.5)
ENABLE_MEMORY = _get("agent", "enable_memory", True)
ENABLE_RAG = _get("agent", "enable_rag", True)
ENABLE_MULTI_AGENT = _get("agent", "enable_multi_agent", True)

# 工具配置
_tools_cfg = config.get("tools", {}) or {}
_code_exec_cfg = _tools_cfg.get("code_executor", {}) or {}
CODE_EXEC_TIMEOUT = _code_exec_cfg.get("timeout", CODE_EXECUTION_TIMEOUT)
CODE_EXEC_MEMORY_LIMIT_MB = _code_exec_cfg.get("memory_limit_mb", 512)
CODE_EXEC_NETWORK_DISABLED = _code_exec_cfg.get("network_disabled", True)

_web_search_cfg = _tools_cfg.get("web_search", {}) or {}
WEB_SEARCH_ENABLED = _web_search_cfg.get("enabled", False)
WEB_SEARCH_API_KEY = _web_search_cfg.get("api_key", "")

# ============================================================
# DeepInvestigate v3.0 新增配置加载
# ============================================================

# HITL 配置
HITL_ENABLED = _get("hitl", "enabled", True)

# Guardrails 配置
GUARDRAILS_INPUT_ENABLED = _get("guardrails", "input", {}).get("enabled", True) if isinstance(_get("guardrails", "input", {}), dict) else True
GUARDRAILS_OUTPUT_PII_MASKING = _get("guardrails", "output", {}).get("pii_masking", True) if isinstance(_get("guardrails", "output", {}), dict) else True

# Checkpoint 配置
CHECKPOINT_DB_PATH = _get("checkpoint", "db_path", "data/checkpoints.db")
CHECKPOINT_TTL_DAYS = _get("checkpoint", "ttl_days", 7)

# Critic 配置
CRITIC_MAX_RETRIES = _get("agent", "critic_max_retries", 2)
