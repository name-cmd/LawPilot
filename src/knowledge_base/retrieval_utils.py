"""Retrieval post-processing: deduplication and relevance formatting."""
from typing import Dict, List, Optional, Tuple

from langchain_core.documents import Document

from src.citation_verifier.article_text import article_body
from src.knowledge_base.law_name_resolver import resolve_law_name


def article_key(doc: Document) -> Tuple[str, str]:
    """Unique key for a law article chunk."""
    law = resolve_law_name(doc.metadata.get("law_name", ""))
    num = doc.metadata.get("article_num", "")
    return law, num


def deduplicate_with_scores(
    results: List[Tuple[Document, float]],
    max_items: Optional[int] = None,
) -> List[Tuple[Document, float]]:
    """Keep first occurrence per (law_name, article_num), preserving rank order."""
    seen = set()
    unique: List[Tuple[Document, float]] = []
    for doc, score in results:
        key = article_key(doc)
        if not key[0] or not key[1] or key in seen:
            continue
        seen.add(key)
        unique.append((doc, score))
        if max_items and len(unique) >= max_items:
            break
    return unique


def format_article_record(
    doc: Document,
    relevance_score: Optional[float] = None,
) -> Dict:
    """API-friendly article dict with clean body text."""
    m = doc.metadata
    body = article_body(doc.page_content)
    record = {
        "law_name": m.get("law_name", ""),
        "article_num": m.get("article_num", ""),
        "content": body,
        "full_text": doc.page_content,
        "status": m.get("status") or "effective",
        "effective_date": m.get("effective_date") or "",
        "repeal_date": m.get("repeal_date") or "",
        "superseded_by": m.get("superseded_by") or "",
    }
    if relevance_score is not None:
        # Chroma returns distance; convert to 0-1 relevance for display
        record["relevance_score"] = round(max(0.0, min(1.0, 1.0 - relevance_score / 2.0)), 3)
    return record


def merge_unique_docs(
    existing: List[Document],
    found: List[Document],
) -> List[Document]:
    """按（法律名, 条号）去重合并两组检索结果（工具检索结果并入初始结果）。"""
    seen = set()
    out: List[Document] = []
    for doc in existing:
        key = article_key(doc)
        if key in seen:
            continue
        seen.add(key)
        out.append(doc)
    for doc in found:
        key = article_key(doc)
        if key in seen:
            continue
        seen.add(key)
        out.append(doc)
    return out
