"""意图路由规则单测（2026-08-09 修复：文档分析以提问为准）。

覆盖设计文档「新意图路由规则」优先级表的全部场景。
"""
from src.pipeline.intent_router import classify_intent

# 非法律文档：文本中故意含「法条」一词——验证「文档文本不再参与涉法判定」
_DOC = [
    {
        "filename": "修改日志.txt",
        "text": "记录律策智枢 LawPilot项目开发日志，涉及法条识别功能与 Vue 3 前端迁移",
    }
]

_HISTORY = [
    {"role": "user", "content": "劳动仲裁需要什么材料？"},
    {"role": "assistant", "content": "需要身份证明、劳动合同等。"},
]


def test_empty():
    assert classify_intent("").intent == "general_non_legal"


def test_greeting():
    assert classify_intent("你好").intent == "greeting"


def test_legal_query():
    assert classify_intent("劳动仲裁怎么申请").intent == "legal_qa"


def test_private_lending_legal_query():
    """修复（2026-08-09）：民间借贷类缺关键词被误判为非法律问题"""
    assert classify_intent("民间借贷利率的合法上限是多少？").intent == "legal_qa"
    assert classify_intent("借款不还怎么办").intent == "legal_qa"
    assert classify_intent("贷款利息太高能起诉吗").intent == "legal_qa"


def test_non_legal_signal():
    assert classify_intent("今天天气怎么样").intent == "general_non_legal"


def test_document_analysis_no_legal_query():
    """修复核心：非法律文档（含法律词）+ 无法律词提问 → 非法律文档分析"""
    r = classify_intent("文档内容说了什么", user_documents=_DOC)
    assert r.intent == "general_non_legal"
    assert "文档" in r.reason


def test_document_with_legal_query():
    """文档 + 法律词提问 → 法律问答（不变）"""
    r = classify_intent("这份合同有什么风险条款", user_documents=_DOC)
    assert r.intent == "legal_qa"


def test_history_legal_context_no_docs():
    """无文档 + 无法律词 + 历史涉法 → 延续法律问答（不变）"""
    r = classify_intent("那怎么办", history=_HISTORY)
    assert r.intent == "legal_qa"


def test_document_analysis_wins_over_history():
    """带文档 + 无法律词 + 历史涉法 → 文档分析优先（修复点）"""
    r = classify_intent("帮我总结这个文档", history=_HISTORY, user_documents=_DOC)
    assert r.intent == "general_non_legal"


def test_short_input():
    assert classify_intent("在吗").intent == "greeting"
