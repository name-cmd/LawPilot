"""文档引文核验单测：回答引用的文档原文必须与上传文档逐字一致。"""
from src.citation_verifier.document_quotes import DocumentQuoteVerifier

_DOC = [{"filename": "劳动合同.txt", "text": "第一条 试用期三个月。甲方应按时支付工资。"}]


def test_quote_found_in_document():
    checks = DocumentQuoteVerifier().verify(
        "合同约定「试用期三个月」，甲方应按时支付工资。", _DOC
    )["document_quote_checks"]
    assert checks and checks[0]["verdict"] == "verified"
    assert checks[0]["found"] is True


def test_quote_not_found_in_document():
    """模型编造条款（「试用期六个月」不在文档中）→ 标 document_mismatch"""
    checks = DocumentQuoteVerifier().verify(
        "合同约定「试用期六个月」明显违法。", _DOC
    )["document_quote_checks"]
    assert checks and checks[0]["verdict"] == "document_mismatch"
    assert checks[0]["found"] is False


def test_law_name_quote_not_treated_as_doc_clause():
    """《劳动合同法》等法条引用不含文档条款信号词 → 不进入文档引文检查"""
    checks = DocumentQuoteVerifier().verify(
        "依据《劳动合同法》第十九条，试用期不得超过六个月。", _DOC
    )["document_quote_checks"]
    assert checks == []


def test_curly_quote_found_in_document():
    """模型常用弯引号“…”引用文档原文（实测百炼输出风格）→ 同样逐字核验"""
    checks = DocumentQuoteVerifier().verify(
        "合同约定“试用期三个月”，甲方应按时支付工资。", _DOC
    )["document_quote_checks"]
    assert checks and checks[0]["verdict"] == "verified"
    assert checks[0]["found"] is True


def test_no_documents_returns_empty():
    assert DocumentQuoteVerifier().verify("任何回答", [])["document_quote_checks"] == []
