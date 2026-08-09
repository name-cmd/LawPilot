"""提示词选择单测（2026-08-09：document_mode 前置，general 带文档走文档分析）。

注：用「三个小节标题必须保留」作为强制三段式提示词的标识——greeting/general/
文档分析提示词中「不要使用【结论】…结构」的否定句也含【结论】字样，不能用
"【结论】" not in 判定。
"""
from src.llm.qwen_model import get_system_prompt

_MANDATORY_TEMPLATE = "三个小节标题必须保留"


def test_legal_default():
    p = get_system_prompt("legal_qa")
    assert _MANDATORY_TEMPLATE in p and "【依据法条】" in p


def test_greeting():
    p = get_system_prompt("greeting")
    assert "寒暄" in p and _MANDATORY_TEMPLATE not in p


def test_general():
    p = get_system_prompt("general_non_legal")
    assert _MANDATORY_TEMPLATE not in p


def test_document_mode():
    """general_non_legal + document_mode → 文档分析提示词（含结尾引导句）"""
    p = get_system_prompt("general_non_legal", document_mode=True)
    assert "总结文档" in p and _MANDATORY_TEMPLATE not in p
    assert "法律咨询" in p


def test_document_mode_priority():
    """document_mode 优先于意图判断（即使 intent=legal_qa）"""
    assert "总结文档" in get_system_prompt("legal_qa", document_mode=True)
