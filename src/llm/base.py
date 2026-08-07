"""统一模型接口：所有引擎（本地推理 / API 引擎）对外契约一致。

阶段八「模型抽象层」：调用方（answer_pipeline / self_consistency / SSE 层）
只依赖本接口，不感知具体引擎。新增引擎只需实现该接口并在注册表登记。
"""
from abc import ABC, abstractmethod
from typing import Dict, Generator, List, Optional


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

    @property
    @abstractmethod
    def model_name(self) -> str:
        """当前默认模型的展示名（如 "Qwen3.7 Plus"）。"""

    @property
    @abstractmethod
    def capabilities(self) -> Dict:
        """能力标签：is_local / is_streaming / price_tier / capabilities 等。"""
