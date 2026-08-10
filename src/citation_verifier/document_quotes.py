"""文档引文核验：回答中引用用户上传文档的句子，与文档原文逐字比对。

场景：合同审查管线。模型可能编造合同条款（引号内内容并非文档原文），
本模块检测并标记，防止「模型说出来的条款」被误当文档事实。
纯字符串逻辑、无外部依赖，可独立单测。
"""
import re
from typing import Dict, List

# 引号样式：中文直角引号、弯引号与书名号（文档名引用也可能是《合同名》）。
# 弯引号「“…”」为百炼 API 实测输出风格（2026-08-10 集成验证发现），漏掉会使
# 文档引文核验在真实生产回答中永远返回空列表，故一并纳入。
_QUOTE_PATTERNS = [
    re.compile(r"「([^」]{2,120})」"),
    re.compile(r"“([^”]{2,120})”"),
    re.compile(r"《([^》]{2,120})》"),
]
# 疑似文档条款内容的信号词（非此信号不判定为文档引文，避免把法条名误报）
_DOC_CLAUSE_HINTS = (
    "甲方", "乙方", "丙方", "条款", "本合同", "本协议",
    "第.{1,4}条", "签字", "盖章", "试用期", "工资", "违约金", "期限", "报酬",
)


def _looks_like_doc_clause(text: str) -> bool:
    return any(re.search(p, text) for p in _DOC_CLAUSE_HINTS)


class DocumentQuoteVerifier:
    """对回答做文档引文检查（返回 document_quote_checks 列表）。"""

    def verify(self, response: str, user_documents: List[Dict]) -> Dict:
        doc_texts = [d.get("text") or "" for d in (user_documents or [])]
        all_text = "\n".join(doc_texts)
        checks = []
        for pattern in _QUOTE_PATTERNS:
            for quote in pattern.findall(response or ""):
                if not _looks_like_doc_clause(quote):
                    continue
                checks.append({
                    "text": quote,
                    "found": quote in all_text,
                    "verdict": "verified" if quote in all_text else "document_mismatch",
                    "in_document": quote in all_text,
                })
        return {"document_quote_checks": checks}
