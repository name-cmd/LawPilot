"""工具循环引擎单测：无工具 / 调工具 / 轮次耗尽 / 出错降级。"""
from langchain_core.documents import Document

from src.agents.agent_loop import AgentToolLoop
from src.agents.trace import AgentStatusEvent
from src.llm.base import ToolCall
from src.pipeline.answer_pipeline import PipelineContext
from src.pipeline.intent_router import IntentResult


class FakeModel:
    """脚本化的假模型：按 scripted 序列依次产出决策/文本。"""

    def __init__(self, scripted):
        self.scripted = list(scripted)
        self.built_messages = None

    def build_messages(self, query, system_prompt, context_docs=None, history=None, intent_hint=None):
        self.built_messages = [{"role": "user", "content": query}]
        return list(self.built_messages)

    def complete_stream_with_tools(self, messages, tools, model_id=None, max_tokens=512):
        item = self.scripted.pop(0)
        if item["kind"] == "text":
            yield ("text", item["text"])
            return
        yield ("tool_calls", item["calls"])

    def generate_stream_messages(self, messages, model_id=None, temperature=None, max_new_tokens=None):
        yield "轮次耗尽兜底回答"

    def generate(self, query, system_prompt=None, temperature=None, max_new_tokens=None,
                 context_docs=None, history=None, intent_hint=None, model_id=None):
        return "兜底回答"


class FakeStore:
    def __init__(self, docs):
        self._docs = docs

    def similarity_search_unique(self, query, k=None):
        return self._docs


def _doc(law, num, text):
    return Document(page_content=text, metadata={"law_name": law, "article_num": num, "status": "effective"})


def _ctx(task_type="legal_qa"):
    intent = IntentResult("legal_qa", 0.9, "test")
    return PipelineContext(
        query="工伤认定和劳动仲裁时效分别是多久？",
        intent=intent,
        generation_query="工伤认定和劳动仲裁时效分别是多久？",
        system_prompt="system",
        context_docs=["参考法条：…"],
        model_id="qwen-turbo",
    )


def test_no_tool_call_streams_answer():
    model = FakeModel([{"kind": "text", "text": "直接回答"}])
    loop = AgentToolLoop(model, FakeStore([]), max_rounds=3)
    events = list(loop.stream(_ctx()))
    assert events == ["直接回答"]
    assert loop.answer == "直接回答"
    assert loop.trace == []
    assert loop.found_docs == []


def test_tool_call_then_final_answer():
    store = FakeStore([(_doc("工伤保险条例", "第十七条", "30日内提出工伤认定申请"), 0.2)])
    model = FakeModel([
        {"kind": "calls", "calls": [ToolCall("c1", "search_articles", {"query": "工伤认定时效", "law_name": "工伤保险条例"})]},
        {"kind": "text", "text": "最终回答"},
    ])
    loop = AgentToolLoop(model, store, max_rounds=3)
    events = list(loop.stream(_ctx()))
    kinds = [type(e) for e in events]
    assert AgentStatusEvent in kinds and str in kinds
    assert loop.answer == "最终回答"
    assert len(loop.trace) == 1
    assert loop.trace[0].tool_name == "search_articles"
    assert loop.trace[0].success is True
    assert loop.found_docs  # 工具检索到的法条被收集


def test_round_exhaustion_falls_back():
    model = FakeModel([
        {"kind": "calls", "calls": [ToolCall("c1", "search_articles", {"query": "x"})]},
        {"kind": "calls", "calls": [ToolCall("c2", "search_articles", {"query": "y"})]},
        {"kind": "calls", "calls": [ToolCall("c3", "search_articles", {"query": "z"})]},
        {"kind": "calls", "calls": [ToolCall("c4", "search_articles", {"query": "w"})]},
    ])
    loop = AgentToolLoop(model, FakeStore([]), max_rounds=3)
    events = list(loop.stream(_ctx()))
    assert loop.answer == "轮次耗尽兜底回答"
    assert len(loop.trace) == 3
    assert any(isinstance(e, AgentStatusEvent) and e.status == "generating" for e in events)


def test_empty_fallback_uses_non_streaming_generate():
    """轮次耗尽后流式兜底为空（部分模型对工具历史返回空流）→ 非流式再问一次，
    保证最终回答不为空（kimi 场景：3 轮全部调工具后兜底空流）。"""
    class EmptyStreamModel(FakeModel):
        def generate_stream_messages(self, messages, model_id=None, temperature=None, max_new_tokens=None):
            if False:
                yield ""  # 保持生成器函数；实际为空流（不产出任何块）

        def generate(self, query, system_prompt=None, temperature=None, max_new_tokens=None,
                     context_docs=None, history=None, intent_hint=None, model_id=None):
            return "非流式兜底回答"

    model = EmptyStreamModel([
        {"kind": "calls", "calls": [ToolCall("c1", "search_articles", {"query": "x"})]},
        {"kind": "calls", "calls": [ToolCall("c2", "search_articles", {"query": "y"})]},
        {"kind": "calls", "calls": [ToolCall("c3", "search_articles", {"query": "z"})]},
    ])
    loop = AgentToolLoop(model, FakeStore([]), max_rounds=3)
    events = list(loop.stream(_ctx()))
    assert "非流式兜底回答" in events
    assert loop.answer == "非流式兜底回答"
    assert len(loop.trace) == 3
    assert any(isinstance(e, AgentStatusEvent) and e.status == "generating" for e in events)


def test_unknown_tool_records_failure_and_continues():
    model = FakeModel([
        {"kind": "calls", "calls": [ToolCall("c1", "no_such_tool", {})]},
        {"kind": "text", "text": "继续回答"},
    ])
    loop = AgentToolLoop(model, FakeStore([]), max_rounds=3)
    events = list(loop.stream(_ctx()))
    assert loop.trace[0].success is False
    assert "未知工具" in loop.trace[0].result_summary
    assert loop.answer == "继续回答"


def test_not_implemented_degrades_to_plain_generation():
    class NoToolsModel(FakeModel):
        def complete_stream_with_tools(self, messages, tools, model_id=None, max_tokens=512):
            raise NotImplementedError("本地引擎不支持函数调用")

    loop = AgentToolLoop(NoToolsModel([]), FakeStore([]), max_rounds=3)
    events = list(loop.stream(_ctx()))
    assert "".join(e for e in events if isinstance(e, str)) == "轮次耗尽兜底回答"
    assert loop.answer == "轮次耗尽兜底回答"


def test_run_non_streaming():
    model = FakeModel([
        {"kind": "calls", "calls": [ToolCall("c1", "search_articles", {"query": "x"})]},
        {"kind": "text", "text": "非流式最终回答"},
    ])
    loop = AgentToolLoop(model, FakeStore([]), max_rounds=3)
    answer, trace = loop.run(_ctx())
    assert answer == "非流式最终回答"
    assert len(trace) == 1
