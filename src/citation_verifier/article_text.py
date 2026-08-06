"""Helpers for normalising stored law article text."""
import re
from typing import List, Optional, Tuple

_CN_DIGIT = {
    "零": 0, "一": 1, "二": 2, "三": 3, "四": 4,
    "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
}

_ITEM_CLAUSE_RE = re.compile(
    r"[（(]([一二三四五六七八九十百零\d]+)[）)]\s*([^（(]+?)(?=(?:[（(]|$))",
    re.DOTALL,
)
_KUAN_RE = re.compile(
    r"第([一二三四五六七八九十百零\d]+)款\s*([^第]+?)(?=第[一二三四五六七八九十百零\d]+款|$)",
    re.DOTALL,
)


def article_body(page_content: str) -> str:
    """Return article text without the 【法律名】第X条 header line."""
    lines = page_content.strip().split("\n")
    if not lines:
        return page_content
    first = lines[0]
    if first.startswith("【") and "】" in first:
        return "\n".join(lines[1:]).strip() or page_content
    return page_content.strip()


def chinese_numeral_to_int(s: str) -> int:
    if not s:
        return 0
    if s.isdigit():
        return int(s)
    if s == "十":
        return 10
    if len(s) == 2 and s[0] == "十" and s[1] in _CN_DIGIT:
        return 10 + _CN_DIGIT[s[1]]
    if len(s) == 2 and s[0] in _CN_DIGIT and s[1] == "十":
        return _CN_DIGIT[s[0]] * 10
    total = 0
    for ch in s:
        if ch in _CN_DIGIT:
            total = total * 10 + _CN_DIGIT[ch]
    return total


def _split_enumerated_clauses(body: str) -> List[Tuple[int, str]]:
    clauses: List[Tuple[int, str]] = []
    for m in _ITEM_CLAUSE_RE.finditer(body):
        idx = chinese_numeral_to_int(m.group(1))
        text = m.group(2).strip().rstrip("；;。.")
        if idx and text:
            clauses.append((idx, text))
    return clauses


def extract_clause_body(
    body: str,
    *,
    item: Optional[int] = None,
    kuan: Optional[int] = None,
) -> str:
    """Return the referenced 款/项 text, or full body if not specified."""
    body = body.strip()
    if not body:
        return body

    if kuan is not None:
        for m in _KUAN_RE.finditer(body):
            if chinese_numeral_to_int(m.group(1)) == kuan:
                return m.group(2).strip().rstrip("；;。.")

    if item is not None:
        for idx, text in _split_enumerated_clauses(body):
            if idx == item:
                return text

    return body


def best_matching_clause(body: str, claim: str, embed_fn) -> str:
    """Pick the enumerated clause in *body* most semantically similar to *claim*."""
    import numpy as np

    clauses = _split_enumerated_clauses(body)
    if not clauses:
        return body

    claim_vec = np.array(embed_fn(claim))
    best_text = body
    best_score = -1.0
    for _, text in clauses:
        ref_vec = np.array(embed_fn(text))
        denom = np.linalg.norm(claim_vec) * np.linalg.norm(ref_vec) + 1e-8
        score = float(np.dot(claim_vec, ref_vec) / denom)
        if score > best_score:
            best_score = score
            best_text = text
    return best_text
