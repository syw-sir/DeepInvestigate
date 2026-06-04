"""
DeepInvestigate v3.0 A2A (Agent-to-Agent) 通信协议模块
"""

from .protocol import A2AMessage, MessageType
from .coordinator import ParallelCoordinator

__all__ = ["A2AMessage", "MessageType", "ParallelCoordinator"]
