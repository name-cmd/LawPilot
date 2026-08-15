"""任务调度器单测：时效查询 / 合同审查 / 兜底回退。"""
import json
import tempfile
from pathlib import Path

from src.pipeline.intent_router import IntentResult, classify_intent
from src.agents.task_scheduler import classify_task

_DOCS = [
    {"filename": "劳动合同.txt", "text": "甲方乙方试用期约定条款……", "format": "txt", "char_count": 20}
]


def _legal_intent(q: str) -> IntentResult:
    return classify_intent(q)


def test_validity_repealed_law_query():
    assert classify_task("婚姻法现在还有效吗？", _legal_intent("婚姻法现在还有效吗？")).task_type == "validity_check"


def test_validity_repeal_wording():
    assert classify_task("合同法废止了吗？", _legal_intent("合同法废止了吗？")).task_type == "validity_check"


def test_validity_not_detected_without_time_wording():
    """提及废止法律但无时效措辞 → 不判时效查询（如咨询具体规定）"""
    assert classify_task("婚姻法对离婚财产分割怎么规定？", _legal_intent("婚姻法对离婚财产分割怎么规定？")).task_type == "legal_qa"


def test_contract_review_with_documents():
    t = classify_task("这份合同有什么风险条款？", _legal_intent("这份合同有什么风险条款？"), _DOCS)
    assert t.task_type == "contract_review"


def test_contract_review_guidance_without_documents():
    t = classify_task("帮我审一下这份合同", _legal_intent("帮我审一下这份合同"), None)
    assert t.task_type == "contract_review"
    assert t.confidence >= 0.8


def test_contract_keyword_fallback_without_docs():
    """「合同到期不续签怎么办」含合同但无审查信号 → 默认法律问答"""
    assert classify_task("合同到期不续签怎么办？", _legal_intent("合同到期不续签怎么办？")).task_type == "legal_qa"


def test_registry_driven_law_names():
    """时效法律名动态取自注册表：把临时注册表写入「专利法」验证不硬编码。"""
    with tempfile.TemporaryDirectory() as d:
        reg = Path(d) / "law_registry.json"
        reg.write_text(json.dumps({"专利法": {"status": "repealed", "repeal_date": "2009-10-01", "superseded_by": "专利法(2008修订)"}}, ensure_ascii=False), encoding="utf-8")
        t = classify_task("专利法还有效吗？", _legal_intent("专利法还有效吗？"), None, registry_path=str(reg))
        assert t.task_type == "validity_check"
        assert t.law_name == "专利法"


def test_default_fallback():
    assert classify_task("劳动仲裁怎么申请？", _legal_intent("劳动仲裁怎么申请？")).task_type == "legal_qa"


def test_contract_clause_question_without_docs_not_review():
    """「劳动合同试用期条款违法怎么办？」是标准法律问答，不应误判合同审查。"""
    assert classify_task("劳动合同试用期条款违法怎么办？", _legal_intent("劳动合同试用期条款违法怎么办？")).task_type == "legal_qa"


def test_document_with_generic_risk_word_not_contract():
    """带非合同文档 + 泛用风险词（如判决书「有什么风险」）→ 不判合同审查。"""
    t = classify_task("这份材料有什么风险？", _legal_intent("这份材料有什么风险？"), _DOCS)
    assert t.task_type == "legal_qa"


def test_non_legal_intent_guard():
    """非 legal_qa 意图（general_non_legal）→ 不做任务细化，直接落回 legal_qa。"""
    t = classify_task("帮我审一下这个游戏", IntentResult("general_non_legal", 0.88, "非法律"), None)
    assert t.task_type == "legal_qa"


def test_judgment_doc_with_generic_risk_word_not_contract():
    """判决书 + 泛用风险词（I2 正则钉住）：legal_qa 意图 + 携带文档 + 「风险」
    但无合同/协议审查信号 → 必须落回 legal_qa，不得误判 contract_review。"""
    q = "判决书里有什么风险需要注意？"
    t = classify_task(q, classify_intent(q), _DOCS)
    assert t.task_type == "legal_qa"
