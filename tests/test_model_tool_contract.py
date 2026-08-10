"""模型层工具契约单测：ToolCall / ToolDecision 数据类行为。"""
from src.llm.base import ToolCall, ToolDecision


def test_tool_call_to_dict():
    tc = ToolCall(id="call_1", name="search_articles", arguments={"query": "工伤认定"})
    assert tc.to_dict() == {
        "id": "call_1",
        "name": "search_articles",
        "arguments": {"query": "工伤认定"},
    }


def test_tool_decision_default_no_calls():
    d = ToolDecision(text="回答")
    assert d.text == "回答"
    assert d.tool_calls == []


def test_tool_decision_with_calls():
    d = ToolDecision(text="", tool_calls=[ToolCall("c1", "search_articles", {})])
    assert len(d.tool_calls) == 1
    assert d.tool_calls[0].name == "search_articles"
