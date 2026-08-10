"""QwenModel 工具接口单测：用假 APIClient 验证消息传递与降级行为。"""
import pytest

from src.llm.base import ToolCall, ToolDecision
from src.llm.qwen_model import QwenModel
from src.agents.tools import TOOLS


class FakeAPIClient:
    """记录调用参数的假客户端（不真正访问网络）。"""

    def __init__(self, decisions=None):
        self.decisions = list(decisions or [])
        self.calls = []

    def complete_with_tools(self, messages, tools, model_id, temperature=0.0, max_tokens=512):
        self.calls.append(("complete_with_tools", messages, tools, model_id, max_tokens))
        return self.decisions.pop(0)

    def complete_stream_with_tools(self, messages, tools, model_id, temperature=0.0, max_tokens=512):
        self.calls.append(("complete_stream_with_tools", messages, tools, model_id, max_tokens))
        yield from self.decisions.pop(0)

    def complete_stream(self, messages, model_id, temperature=0.4, max_tokens=1024):
        self.calls.append(("complete_stream", messages, model_id))
        yield "流式文本"


def _make_model(decisions):
    m = QwenModel(provider="api", api_client=FakeAPIClient(decisions))
    fake = m._api
    m._get_api_client = lambda spec: fake  # 绕过 base_url 客户端缓存，注入假客户端
    return m


def test_complete_with_tools_passes_messages_and_tools():
    m = _make_model([ToolDecision(text="", tool_calls=[ToolCall("c1", "search_articles", {"query": "x"})])])
    msgs = [{"role": "user", "content": "问题"}]
    dec = m.complete_with_tools(msgs, TOOLS, model_id="qwen-turbo")
    assert dec.tool_calls[0].name == "search_articles"
    assert m._api.calls[0][1] == msgs and m._api.calls[0][2] == TOOLS
    assert m._api.calls[0][3] == "qwen-turbo"


def test_complete_with_tools_text_result():
    m = _make_model([ToolDecision(text="直接回答", tool_calls=[])])
    dec = m.complete_with_tools([{"role": "user", "content": "q"}], TOOLS, model_id="qwen-turbo")
    assert dec.text == "直接回答" and dec.tool_calls == []


def test_stream_with_tools_yields_text_then_calls():
    def gen():
        yield ("text", "分析中")
        yield ("tool_calls", [ToolCall("c1", "search_articles", {"query": "x"})])
    m = _make_model([gen()])
    out = list(m.complete_stream_with_tools([{"role": "user", "content": "q"}], TOOLS, model_id="qwen-turbo"))
    assert out[0] == ("text", "分析中")
    assert out[1][0] == "tool_calls" and out[1][1][0].name == "search_articles"


def test_generate_stream_messages_delegates():
    m = _make_model([])
    m._get_api_client = lambda spec: m._api
    chunks = list(m.generate_stream_messages([{"role": "user", "content": "q"}], model_id="qwen-turbo"))
    assert chunks == ["流式文本"]
    assert m._api.calls[0][0] == "complete_stream"


def test_local_engine_raises_not_implemented():
    m = QwenModel(provider="local")
    assert m.supports_tools("qwen-turbo") is True
    assert m.supports_tools("local") is False  # "local" 不在注册表 → 视为不支持
    with pytest.raises(NotImplementedError):
        m.complete_with_tools([{"role": "user", "content": "q"}], TOOLS)
