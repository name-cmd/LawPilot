"""Format retrieved law documents for LLM prompts."""
from typing import List
from langchain_core.documents import Document
from src.citation_verifier.article_text import article_body


def format_retrieved_articles(docs: List[Document]) -> str:
    """Numbered reference block with explicit law name and article number."""
    if not docs:
        return ""
    blocks = []
    for i, doc in enumerate(docs, 1):
        m = doc.metadata
        law = m.get("law_name", "")
        num = m.get("article_num", "")
        body = article_body(doc.page_content)
        blocks.append(
            f"[参考{i}] 《{law}》{num}\n"
            f"原文：{body}"
        )
    return "\n\n".join(blocks)
