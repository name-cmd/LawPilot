"""工具调用轨迹与智能体状态事件的数据模型。"""
from dataclasses import dataclass
from typing import Any, Dict, List, Union


@dataclass
class ToolTraceStep:
    """轨迹中一步工具调用的完整记录（随 done 事件返回，详情面板展示）。"""

    step: int
    tool_name: str
    arguments: Dict[str, Any]
    result_summary: str
    success: bool = True
    cost_ms: int = 0

    def to_dict(self) -> dict:
        return {
            "step": self.step,
            "tool_name": self.tool_name,
            "arguments": self.arguments,
            "result_summary": self.result_summary,
            "success": self.success,
            "cost_ms": self.cost_ms,
        }


@dataclass
class AgentStatusEvent:
    """SSE agent_status 事件的负载（前端生成中状态行）。"""

    step: int
    tool_name: str = ""
    status: str = "running"   # running | done | error | generating
    detail: str = ""
    result_summary: str = ""

    def to_dict(self) -> dict:
        return {
            "step": self.step,
            "tool_name": self.tool_name,
            "status": self.status,
            "detail": self.detail,
            "result_summary": self.result_summary,
        }


# 智能体流式事件：状态事件或文本块
AgentEvent = Union[AgentStatusEvent, str]
