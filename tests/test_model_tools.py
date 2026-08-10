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


def test_apiclient_complete_with_tools_retries_on_rate_limit():
    """APIClient.complete_with_tools：可重试错误自动退避重试，重试后成功并返回正确决策。

    假客户端模拟「前两次抛限流错误、第三次成功」两条路径；
    断言调用次数 = 1 + 重试次数，且最终决策解析正确（验证重试确实发生）。
    """
    from types import SimpleNamespace

    import httpx
    from openai import RateLimitError

    from src.llm.api_client import APIClient

    attempts = {"n": 0}

    def fake_create(**kwargs):
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise RateLimitError(
                "rate limited",
                response=httpx.Response(429, request=httpx.Request("POST", "http://test")),
                body=None,
            )
        # 第三次成功：返回带工具调用的响应（message.tool_calls 结构仿 OpenAI SDK）
        return SimpleNamespace(
            usage=None,
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content=None,
                        tool_calls=[
                            SimpleNamespace(
                                id="call_1",
                                function=SimpleNamespace(
                                    name="search_articles",
                                    arguments='{"query": "x"}',
                                ),
                            )
                        ],
                    )
                )
            ],
        )

    client = APIClient(api_key="test-key")
    client._client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create))
    )
    client._sleep_backoff = lambda attempt: None  # 跳过真实退避等待，测试提速

    dec = client.complete_with_tools(
        [{"role": "user", "content": "q"}], TOOLS, model_id="qwen-turbo"
    )
    assert attempts["n"] == 3  # 1 次初始调用 + 2 次重试
    assert dec.tool_calls[0].name == "search_articles"
    assert dec.tool_calls[0].arguments == {"query": "x"}
