"""
Level 1 — Regex-based citation extractor.
Extracts structured citation objects from LLM response text.
"""
import re
from dataclasses import dataclass
from typing import List, Optional

from .sentence_utils import (
    law_names_in_sentence,
    sentence_at,
    sentence_has_article_citation,
    split_sentences,
)

# Primary pattern: 《法律名》第N条  (with optional 款/项)
_CITATION_RE = re.compile(
    r"《([^》]{2,30})》"
    r"第([一二三四五六七八九十百千零\d]+)条"
    r"(?:第([一二三四五六七八九十]+)款)?"
    r"(?:第([一二三四五六七八九十]+)项)?"
)

# Same-law continuation: 以及第七百八十五条
_CONTINUATION_RE = re.compile(
    r"(?:以及|及|另见|参见|见)\s*"
    r"第([一二三四五六七八九十百千零\d]+)条"
    r"(?:第([一二三四五六七八九十]+)款)?"
    r"(?:第([一二三四五六七八九十]+)项)?"
)

# Quoted statutory text after a citation (within ~160 chars)
_QUOTE_AFTER_CITATION_RE = re.compile(
    r"(?:规定|称|载明|原文)?[:：]\s*"
    r"[「“\"']([^」”\"']{8,500})[」”\"\']"
)

# Model cites an article only to say it does not apply
_DENIAL_AFTER_CITATION_RE = re.compile(
    r"(?:并未|并没有|不涉及|与[^。，；]{0,20}无关|不适用|并未直接|无相关规定|没有规定|未规定)"
)

_DIGIT_MAP = {
    "零": 0, "一": 1, "二": 2, "三": 3, "四": 4,
    "五": 5, "六": 6, "七": 7, "八": 8, "九": 9,
}
_UNIT_MAP = {"十": 10, "百": 100, "千": 1000}


def _chinese_to_int(s: str) -> int:
    result, current = 0, 0
    for ch in s:
        if ch in _DIGIT_MAP:
            current = _DIGIT_MAP[ch]
        elif ch in _UNIT_MAP:
            unit = _UNIT_MAP[ch]
            if current == 0 and unit == 10:
                current = 1
            result += current * unit
            current = 0
        elif ch.isdigit():
            current = current * 10 + int(ch)
    return result + current


def _parse_num(s: str) -> int:
    return int(s) if s.isdigit() else _chinese_to_int(s)


def _law_name_before(text: str, pos: int) -> Optional[str]:
    """Nearest 《法律名》 before position (for continuation citations)."""
    prefix = text[:pos]
    matches = list(_CITATION_RE.finditer(prefix))
    if not matches:
        return None
    return matches[-1].group(1)


def _is_denial_mention(text: str, cite_end: int) -> bool:
    """Citation used only to deny relevance (e.g. 第X条并未涉及…)."""
    snippet = text[cite_end : cite_end + 48]
    return bool(_DENIAL_AFTER_CITATION_RE.search(snippet))


def extract_quote_after(text: str, citation_end: int, window: int = 160) -> Optional[str]:
    """Extract verbatim quote following a citation span."""
    snippet = text[citation_end : citation_end + window]
    m = _QUOTE_AFTER_CITATION_RE.search(snippet)
    if m:
        return m.group(1).strip()
    return None


@dataclass
class Citation:
    raw_text: str       # original span in response
    law_name: str       # "民法典"
    article_num: str    # "第1184条" or "" for law-level
    article_num_int: int
    context: str        # ±150 chars around the citation
    position: int       # byte offset in text
    quoted_text: Optional[str] = None
    is_irrelevant_mention: bool = False
    arguing_sentence: str = ""
    clause_kuan: Optional[int] = None
    clause_item: Optional[int] = None
    is_law_level: bool = False
    resolved_article_num: str = ""  # filled after semantic article resolution


class CitationExtractor:
    def extract(self, text: str) -> List[Citation]:
        citations: List[Citation] = []
        seen: set = set()
        sentences_with_article: set = set()

        def _add(
            raw: str,
            law_name: str,
            num_str: str,
            pos: int,
            cite_end: int,
            *,
            clause_kuan: Optional[str] = None,
            clause_item: Optional[str] = None,
            is_law_level: bool = False,
        ) -> None:
            article_num = f"第{num_str}条" if num_str else ""
            key = (law_name, article_num, clause_kuan or "", clause_item or "", is_law_level, pos)
            if key in seen:
                return
            seen.add(key)

            arguing = sentence_at(text, pos)
            if not is_law_level:
                sentences_with_article.add(arguing)

            citations.append(Citation(
                raw_text=raw,
                law_name=law_name,
                article_num=article_num,
                article_num_int=_parse_num(num_str) if num_str else 0,
                context=text[max(0, pos - 150) : min(len(text), pos + 150)],
                position=pos,
                quoted_text=extract_quote_after(text, cite_end) if not is_law_level else None,
                is_irrelevant_mention=_is_denial_mention(text, cite_end) if not is_law_level else False,
                arguing_sentence=arguing,
                clause_kuan=_parse_num(clause_kuan) if clause_kuan else None,
                clause_item=_parse_num(clause_item) if clause_item else None,
                is_law_level=is_law_level,
            ))

        for m in _CITATION_RE.finditer(text):
            _add(
                m.group(0), m.group(1), m.group(2), m.start(), m.end(),
                clause_kuan=m.group(3), clause_item=m.group(4),
            )

        for m in _CONTINUATION_RE.finditer(text):
            law_name = _law_name_before(text, m.start())
            if not law_name:
                continue
            _add(
                m.group(0), law_name, m.group(1), m.start(), m.end(),
                clause_kuan=m.group(2), clause_item=m.group(3),
            )

        # Law-level: sentence cites 《法律名》for argumentation without 第X条
        for sent, start, _ in split_sentences(text):
            if len(sent) < 16:
                continue
            if sent in sentences_with_article:
                continue
            if sentence_has_article_citation(sent):
                continue
            for law_name in law_names_in_sentence(sent):
                m = re.search(rf"《{re.escape(law_name)}》", sent)
                pos = start + (m.start() if m else 0)
                raw = m.group(0) if m else f"《{law_name}》"
                cite_end = pos + len(raw)
                _add(
                    raw, law_name, "", pos, cite_end, is_law_level=True,
                )

        citations.sort(key=lambda c: c.position)
        return citations
