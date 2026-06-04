"""
输入安全护栏

检测用户输入中的敏感内容，拦截不合规请求。
"""

from __future__ import annotations

import re
from typing import Optional, Tuple

DEFAULT_BLOCKED_PATTERNS = [
    r"(政治敏感|反动|颠覆国家)",
    r"(色情|淫秽|成人内容)",
    r"(暴力恐怖|极端主义)",
]


class InputGuard:
    """输入安全护栏"""

    def __init__(self, blocked_patterns: list[str] | None = None):
        self.patterns = blocked_patterns or DEFAULT_BLOCKED_PATTERNS

    def check(self, text: str) -> Tuple[bool, Optional[str]]:
        for pattern in self.patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return False, f"输入包含敏感内容，匹配规则: {pattern}"
        return True, None
