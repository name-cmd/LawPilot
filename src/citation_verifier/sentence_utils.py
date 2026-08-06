"""Split LLM responses into sentences and locate citing spans."""
import re
from typing import List, Tuple

_SENTENCE_RE = re.compile(r"[^。！？；\n]+[。！？；]?")
_ARTICLE_IN_SENTENCE_RE = re.compile(
    r"第[一二三四五六七八九十百千零\d]+条"
    r"(?:第[一二三四五六七八九十]+款)?"
    r"(?:第[一二三四五六七八九十]+项)?"
)
_LAW_BOOK_RE = re.compile(r"《([^》]{2,30})》")


def split_sentences(text: str) -> List[Tuple[str, int, int]]:
    """Return (sentence, start, end) tuples."""
    out: List[Tuple[str, int, int]] = []
    for m in _SENTENCE_RE.finditer(text):
        s = m.group(0).strip()
        if s:
            out.append((s, m.start(), m.end()))
    return out


def sentence_at(text: str, position: int) -> str:
    """Return the sentence containing *position*."""
    for sent, start, end in split_sentences(text):
        if start <= position < end:
            return sent
    return text[max(0, position - 120) : min(len(text), position + 120)].strip()


def sentence_has_article_citation(sentence: str) -> bool:
    return bool(_ARTICLE_IN_SENTENCE_RE.search(sentence))


def law_names_in_sentence(sentence: str) -> List[str]:
    return _LAW_BOOK_RE.findall(sentence)
