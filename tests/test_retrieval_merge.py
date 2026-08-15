"""检索多查询合并策略单测（2026-08-09 修复：主查询优先，扩展查询补位）。

复现场景：「离婚冷静期是多长时间？」的扩展查询「离婚 夫妻共同财产 子女抚养」
命中财产条款（相关度更高），旧逻辑按相关度全局排序把真正相关的
民法典第1077条（冷静期）挤出 top-k → 模型检索不到法条依据。
"""
from langchain_core.documents import Document

from src.pipeline.answer_pipeline import AnswerPipeline

merge = AnswerPipeline._merge_query_results


def _doc(law: str, num: str) -> Document:
    return Document(
        page_content=f"{law}第{num}条正文",
        metadata={"law_name": law, "article_num": num},
    )


def test_primary_query_first():
    """主查询命中即使相关度较低也应排在扩展查询命中之前（1077 不再被挤出）"""
    primary = [(_doc("民法典", "第一千零七十七条"), 0.6834)]
    expansion = [
        (_doc("民法典", "第一千零八十七条"), 0.4683),
        (_doc("民法典", "第一千零八十九条"), 0.5109),
    ]
    out = merge([primary, expansion], k=3)
    nums = [d.metadata["article_num"] for d, _ in out]
    assert nums == ["第一千零七十七条", "第一千零八十七条", "第一千零八十九条"]


def test_dedupe_across_queries():
    """同一条文出现在多个查询结果中只保留一份（按法律名+条号去重）"""
    q1 = [(_doc("民法典", "第一千零七十七条"), 0.6834)]
    q2 = [(_doc("民法典", "第一千零七十七条"), 0.60)]
    out = merge([q1, q2], k=5)
    assert len(out) == 1


def test_k_limit():
    """结果数不超过 k"""
    lists = [
        [(_doc("法A", f"第{i}条"), 0.9) for i in range(1, 6)],
        [(_doc("法B", f"第{i}条"), 0.5) for i in range(1, 6)],
    ]
    out = merge(lists, k=4)
    assert len(out) == 4
    # 主查询优先：前 4 条全部来自第一个查询
    assert all(d.metadata["law_name"] == "法A" for d, _ in out)


def test_empty():
    assert merge([], k=5) == []
    assert merge([[], []], k=5) == []


def test_merge_unique_docs():
    """工具检索结果与初始检索结果按（法律名, 条号）去重合并"""
    from src.knowledge_base.retrieval_utils import merge_unique_docs

    def d(law, num):
        return Document(page_content=f"{law}{num}内容", metadata={"law_name": law, "article_num": num})

    merged = merge_unique_docs([d("劳动合同法", "第38条")], [d("劳动合同法", "第38条"), d("工伤保险条例", "第17条")])
    assert len(merged) == 2
    assert merged[1].metadata["law_name"] == "工伤保险条例"


def test_standalone_question_does_not_inherit_unrelated_history():
    """新问题点明行政处罚时，历史中的行政复议不能污染向量检索。"""
    history = [
        {"role": "user", "content": "行政复议申请期限是多久？"},
        {"role": "assistant", "content": "……"},
        {"role": "user", "content": "行政复议机关如何审理？"},
    ]
    query = "行政处罚的种类有哪些？"
    assert AnswerPipeline._build_retrieval_query(query, history) == query


def test_contextual_follow_up_keeps_recent_user_history():
    """“上述决定怎么办”缺少对象，仍应继承上文以维持多轮问答。"""
    history = [
        {"role": "user", "content": "行政机关作出罚款决定后怎么办？"},
        {"role": "assistant", "content": "……"},
    ]
    query = "对上述决定不服怎么办？"
    combined = AnswerPipeline._build_retrieval_query(query, history)
    assert combined == "行政机关作出罚款决定后怎么办？ 对上述决定不服怎么办？"
