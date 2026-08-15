"""统一模型接口：所有引擎（本地推理 / API 引擎）对外契约一致。

阶段八「模型抽象层」：调用方（answer_pipeline / self_consistency / SSE 层）
只依赖本接口，不感知具体引擎。新增引擎只需实现该接口并在注册表登记。
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Generator, List, Optional, Tuple


@dataclass
class ToolCall:
    """模型决定调用的一次工具调用（参数已解析为 Python 对象）。"""

    id: str
    name: str
    arguments: Dict[str, Any]

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "arguments": self.arguments}


@dataclass
class ToolDecision:
    """一次工具决策的结果：要么给出文本（无工具调用），要么给出工具调用列表。"""

    text: str
    tool_calls: List[ToolCall] = field(default_factory=list)


class BaseLLMModel(ABC):
    @abstractmethod
    def generate(
        self,
        query: str,
        system_prompt: str = None,
        temperature: float = None,
        max_new_tokens: int = None,
        context_docs: List[str] = None,
        history: Optional[List[Dict[str, str]]] = None,
        intent_hint: Optional[str] = None,
        model_id: Optional[str] = None,
    ) -> str:
        """非流式生成完整回答。model_id 为空时使用引擎默认模型。"""

    @abstractmethod
    def generate_stream(
        self,
        query: str,
        system_prompt: str = None,
        temperature: float = None,
        max_new_tokens: int = None,
        context_docs: List[str] = None,
        history: Optional[List[Dict[str, str]]] = None,
        intent_hint: Optional[str] = None,
        model_id: Optional[str] = None,
    ) -> Generator[str, None, None]:
        """流式生成，逐段 yield 文本。"""

    @abstractmethod
    def complete_with_tools(
        self,
        messages: List[Dict[str, str]],
        tools: List[Dict],
        model_id: Optional[str] = None,
        max_tokens: int = 512,
    ) -> ToolDecision:
        """非流式工具决策：模型返回文本（无工具调用）或工具调用列表。

        本地引擎不支持函数调用 → 抛 NotImplementedError（调用方降级为普通生成）。
        """

    @abstractmethod
    def complete_stream_with_tools(
        self,
        messages: List[Dict[str, str]],
        tools: List[Dict],
        model_id: Optional[str] = None,
        max_tokens: int = 512,
    ) -> Generator[Tuple[str, Any], None, None]:
        """流式工具决策：yield ("text", str) 文本块；流结束若带工具调用，
        则作为本轮 ("tool_calls", List[ToolCall]) 事件（在文本块之后 yield）。
        本地引擎不支持函数调用 → 抛 NotImplementedError。
        """

    @abstractmethod
    def generate_stream_messages(
        self,
        messages: List[Dict[str, str]],
        model_id: Optional[str] = None,
        temperature: float = None,
        max_new_tokens: int = None,
    ) -> Generator[str, None, None]:
        """按原始消息列表流式生成（工具对话历史已在 messages 中），逐段 yield 文本。"""

    @property
    @abstractmethod
    def model_name(self) -> str:
        """当前默认模型的展示名（如 "Qwen3.7 Plus"）。"""

    @property
    @abstractmethod
    def capabilities(self) -> Dict:
        """能力标签：is_local / is_streaming / price_tier / capabilities 等。"""
