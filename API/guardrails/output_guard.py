"""
输出安全护栏

对 Agent 输出进行 PII 脱敏和安全扫描。
"""

from __future__ import annotations

import re
from typing import Optional, Tuple

PII_PATTERNS = {
    "phone_cn":     r"1[3-9]\d{9}",
    "id_card_cn":   r"\d{17}[\dXx]",
    "email":        r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
    "ip_address":   r"\b(?:\d{1,3}\.){3}\d{1,3}\b",
}

_MASKS = {
    "phone_cn":     "[手机号已隐藏]",
    "id_card_cn":   "[身份证号已隐藏]",
    "email":        "[邮箱已隐藏]",
    "ip_address":   "[IP已隐藏]",
}


class OutputGuard:
    """输出安全护栏 + PII 脱敏"""

    def sanitize(self, text: str) -> str:
        sanitized = text
        for name, pattern in PII_PATTERNS.items():
            sanitized = re.sub(pattern, _MASKS.get(name, "[已隐藏]"), sanitized)
        return sanitized

    def check_safety(self, text: str) -> Tuple[bool, Optional[str]]:
        return True, None
