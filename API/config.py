"""
config.py — 兼容性别名

历史上 file_api.py 等模块写的是 `from config import ...`，
但实际配置在 config_deepseek.py。这里做一个透传别名，
避免改动 v1 文件。
"""

from config_deepseek import *  # noqa: F401,F403
from config_deepseek import (  # noqa: F401
    VALID_FILE_PURPOSES,
    FILE_STORAGE_DIR,
)
