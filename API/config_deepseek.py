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
