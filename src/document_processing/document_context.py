"""Format user-uploaded documents for LLM context injection."""
from typing import Dict, List


def format_user_documents(docs: List[Dict]) -> str:
    """Build a reference block for user contract / document content."""
    if not docs:
        return ""
    blocks = []
    for i, doc in enumerate(docs, 1):
        filename = (doc.get("filename") or f"文档{i}").strip()
        text = (doc.get("text") or "").strip()
        if not text:
            continue
        blocks.append(f"[用户文档{i}] {filename}\n{text}")
    if not blocks:
        return ""
    return (
        "用户上传文档（可引用段落内容辅助分析，非国家官方法条；"
        "引用时请注明来自哪份文档）：\n\n"
        + "\n\n".join(blocks)
    )
