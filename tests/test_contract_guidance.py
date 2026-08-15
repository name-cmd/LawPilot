"""合同审查无文档礼貌引导单测：run() 与 prepare_context+generate_answer_stream 双路径零 LLM 调用。"""
from src.pipeline.answer_pipeline import (
    AnswerPipeline,
    _CONTRACT_GUIDANCE_MESSAGE,
)


class FakeModel:
    """假模型：生成调用必须被短路拦截，一旦被调用即断言失败。"""

    def generate(self, *args, **kwargs):
        raise AssertionError("不应被调用：无文档合同审查必须零 LLM 调用")

    def generate_stream(self, *args, **kwargs):
        raise AssertionError("不应被调用：无文档合同审查必须零 LLM 调用")


def _pipeline() -> AnswerPipeline:
    return AnswerPipeline(store=None, model=FakeModel(), verifier=None)


def test_run_contract_review_without_docs_short_circuits():
    """run()：无文档 contract_review → 不调 LLM，answer 为引导文案，结构同 _run_non_legal。"""
    result = _pipeline().run("帮我审一下这份合同")

    assert result["answer"] == _CONTRACT_GUIDANCE_MESSAGE
    assert result["use_rag"] is False
    assert result["rag_used"] is False
    assert result["retrieved_articles"] == []
    assert result["trust"] is None
    assert result["consistency"] is None
    assert result["citation_verification"]["extracted_citations"] == []
    assert result["task"]["task_type"] == "contract_review"


def test_prepare_context_and_stream_short_circuit():
    """prepare_context + generate_answer_stream：短路文本直接输出，不调模型。"""
    pipeline = _pipeline()
    ctx = pipeline.prepare_context("帮我审一下这份合同")

    assert ctx.short_circuit_text == _CONTRACT_GUIDANCE_MESSAGE
    assert ctx.generation_query == _CONTRACT_GUIDANCE_MESSAGE
    assert ctx.use_rag is False
    assert ctx.task.task_type == "contract_review"

    chunks = list(pipeline.generate_answer_stream(ctx))
    assert chunks == [_CONTRACT_GUIDANCE_MESSAGE]


def test_contract_review_with_docs_keeps_llm_path():
    """携带文档的 contract_review 不走短路（仍走 LLM 路径，此处由假模型断言拦截）。"""
    pipeline = _pipeline()
    docs = [
        {"filename": "劳动合同.txt", "text": "试用期 3 个月，工资 5000 元……", "format": "txt", "char_count": 20}
    ]
    ctx = pipeline.prepare_context(
        "这份合同有什么风险条款？", use_rag=False, user_documents=docs
    )

    assert ctx.short_circuit_text is None
    assert ctx.task.task_type == "contract_review"
