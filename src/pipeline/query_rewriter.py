"""Pre-retrieval query cleaning and legal-intent expansion."""
import re
from dataclasses import dataclass
from typing import List

_PII_NOISE_PATTERNS = [
    (r"身份证\s*\d{6}\*+\d{4}", "[个人信息]"),
    (r"身份证\s*号?\s*\d{17}[\dXx]", "[个人信息]"),
    (r"身份证\s*号?", "[个人信息]"),
    (r"手机号?\s*1[3-9]\d{9}", "[联系方式]"),
    (r"(?<!\d)1[3-9]\d{9}(?!\d)", "[联系方式]"),
    (r"银行卡\s*号?\s*\d[\d\*]{10,}", "[银行卡信息]"),
    (r"\d{17}[\dXx]", "[个人信息]"),
]

_INTENT_EXPANSIONS = [
    (
        r"辞退|被开除|被解雇|被裁员|无故辞退|违法辞退|开除",
        "违法解除劳动合同 经济补偿金 赔偿金 劳动仲裁 维权",
    ),
    (
        r"拖欠工资|不发工资|欠薪|克扣工资",
        "拖欠劳动报酬 劳动监察 劳动仲裁",
    ),
    (
        r"工伤|工亡|伤残",
        "工伤认定 工伤保险待遇 赔偿",
    ),
    (
        r"租房|租赁|押金不退",
        "房屋租赁 押金 违约责任",
    ),
    (
        r"离婚|抚养权|财产分割",
        "离婚 夫妻共同财产 子女抚养",
    ),
    (
        r"交通事故|肇事|理赔",
        "机动车交通事故 责任认定 损害赔偿",
    ),
]

_FOCUS_HINTS = [
    (r"辞退|被开除|被解雇|被裁员|开除", "违法解除劳动合同及维权途径"),
    (r"拖欠工资|欠薪", "追索劳动报酬"),
    (r"工伤", "工伤认定与待遇"),
    (r"租房|租赁|押金", "房屋租赁纠纷"),
    (r"离婚", "离婚与财产子女问题"),
]


@dataclass
class RewriteResult:
    original: str
    cleaned: str
    retrieval_queries: List[str]
    core_focus: str
    pii_stripped: bool

    def to_dict(self) -> dict:
        return {
            "original": self.original,
            "cleaned": self.cleaned,
            "retrieval_queries": self.retrieval_queries,
            "core_focus": self.core_focus,
            "pii_stripped": self.pii_stripped,
        }


def _extract_core_focus(query: str, cleaned: str) -> str:
    for pat, focus in _FOCUS_HINTS:
        if re.search(pat, query) or re.search(pat, cleaned):
            return focus
    text = cleaned or query
    text = re.sub(r"\[个人信息\]|\[联系方式\]|\[银行卡信息\]", "", text)
    text = re.sub(r"\s+", " ", text).strip(" ，,。.")
    return text[:80] if text else query[:80]


def rewrite_for_retrieval(query: str) -> RewriteResult:
    """Remove PII noise and build retrieval query variants."""
    original = (query or "").strip()
    cleaned = original
    pii_stripped = False

    for pat, repl in _PII_NOISE_PATTERNS:
        new = re.sub(pat, repl, cleaned)
        if new != cleaned:
            pii_stripped = True
            cleaned = new

    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    expansions: List[str] = []
    for pat, expansion in _INTENT_EXPANSIONS:
        if re.search(pat, original) or re.search(pat, cleaned):
            expansions.append(expansion)

    retrieval_queries = [cleaned]
    if expansions:
        retrieval_queries.append(" ".join(expansions))
    if cleaned != original and cleaned not in retrieval_queries:
        retrieval_queries.insert(0, cleaned)

    # dedupe preserving order
    seen = set()
    unique_queries: List[str] = []
    for q in retrieval_queries:
        q = q.strip()
        if q and q not in seen:
            seen.add(q)
            unique_queries.append(q)

    core_focus = _extract_core_focus(original, cleaned)

    return RewriteResult(
        original=original,
        cleaned=cleaned or original,
        retrieval_queries=unique_queries or [original],
        core_focus=core_focus,
        pii_stripped=pii_stripped,
    )


def distance_to_relevance(distance: float) -> float:
    """Convert Chroma L2 distance to 0-1 relevance (same as retrieval_utils)."""
    return max(0.0, min(1.0, 1.0 - distance / 2.0))


def is_retrieval_relevant(distance: float, min_relevance: float) -> bool:
    return distance_to_relevance(distance) >= min_relevance
