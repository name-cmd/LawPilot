"""Resolve cited law names to canonical names used in the vector store metadata."""
import json
from pathlib import Path
from typing import List, Optional

# 兜底列表：仅当 data/processed/ 不可读时使用（正常运行时从 processed JSON 动态构建）
_FALLBACK_KNOWN_LAWS = (
    "民法典", "宪法", "劳动法", "劳动合同法", "民事诉讼法", "婚姻法",
    "刑法", "公司法", "消费者权益保护法", "道路交通安全法",
    "工伤保险条例", "劳动合同法实施条例", "社会保险法", "劳动争议调解仲裁法",
    "劳动争议案件适用法律问题的解释（一）", "劳动争议案件适用法律问题的解释（二）",
    "民事诉讼法解释",
    "行政处罚法", "行政许可法", "行政复议法", "行政诉讼法",
    "产品质量法", "食品安全法", "旅游法", "广告法",
    "著作权法", "商标法", "专利法", "刑事诉讼法", "反电信网络诈骗法",
    "民法典婚姻家庭编解释（一）", "民法典婚姻家庭编解释（二）", "民法典合同编通则解释",
)


def _load_known_laws() -> tuple:
    """从 data/processed/*.json 动态构建法律名清单（新增法律无需改代码）。"""
    from src.config import Config

    names: List[str] = []
    try:
        for p in sorted(Path(Config.PROCESSED_DATA_DIR).glob("*.json")):
            if p.name == "law_repeals.json":
                continue
            data = json.loads(p.read_text(encoding="utf-8"))
            title = data.get("title") or p.stem
            if title and title not in names:
                names.append(title)
    except Exception:
        names = []
    return tuple(names) if names else _FALLBACK_KNOWN_LAWS


# Canonical names match data/raw/*.md filename stems（自动从 processed JSON 构建）。
KNOWN_LAWS = _load_known_laws()

_ALIASES = {
    "民法": "民法典",
    "消保法": "消费者权益保护法",
    "消费者法": "消费者权益保护法",
    "道交法": "道路交通安全法",
    "道路交通法": "道路交通安全法",
    "工伤条例": "工伤保险条例",
    "劳动仲裁法": "劳动争议调解仲裁法",
    "劳动争议仲裁法": "劳动争议调解仲裁法",
    "民诉法解释": "民事诉讼法解释",
    "民事诉讼法司法解释": "民事诉讼法解释",
    "劳动争议解释一": "劳动争议案件适用法律问题的解释（一）",
    "劳动争议解释二": "劳动争议案件适用法律问题的解释（二）",
    "行罚法": "行政处罚法",
    "行政处罚": "行政处罚法",
    "行政许可": "行政许可法",
    "行政复议": "行政复议法",
    "行诉法": "行政诉讼法",
    "行政诉讼": "行政诉讼法",
    "产品质量": "产品质量法",
    "食品安全": "食品安全法",
    "旅游": "旅游法",
    "广告": "广告法",
    "著作权": "著作权法",
    "版权法": "著作权法",
    "商标": "商标法",
    "专利": "专利法",
    "刑诉法": "刑事诉讼法",
    "刑事诉讼": "刑事诉讼法",
    "反诈法": "反电信网络诈骗法",
    "电信网络诈骗法": "反电信网络诈骗法",
    "婚姻家庭编解释一": "民法典婚姻家庭编解释（一）",
    "婚姻家庭编解释二": "民法典婚姻家庭编解释（二）",
    "民法典婚姻家庭编司法解释（一）": "民法典婚姻家庭编解释（一）",
    "民法典婚姻家庭编司法解释（二）": "民法典婚姻家庭编解释（二）",
    "合同编通则解释": "民法典合同编通则解释",
    "民法典合同编通则司法解释": "民法典合同编通则解释",
}

_PREFIX = "中华人民共和国"


def _find_canonical(name: str) -> Optional[str]:
    if name in KNOWN_LAWS:
        return name
    if name in _ALIASES:
        return _ALIASES[name]
    if name.startswith(_PREFIX):
        stripped = name[len(_PREFIX) :].strip()
        if stripped in KNOWN_LAWS:
            return stripped
        if stripped in _ALIASES:
            return _ALIASES[stripped]
    for canonical in sorted(KNOWN_LAWS, key=len, reverse=True):
        if name.endswith(canonical):
            return canonical
    return None


def resolve_law_name(cited_name: str) -> str:
    """Return the preferred canonical law name for a cited name."""
    candidates = law_name_candidates(cited_name)
    return candidates[0] if candidates else (cited_name or "").strip()


def law_name_candidates(cited_name: str) -> List[str]:
    """Return deduplicated candidate names to try, best match first."""
    name = (cited_name or "").strip()
    if not name:
        return []

    ordered: List[str] = []
    seen: set = set()

    def add(candidate: str) -> None:
        c = candidate.strip()
        if c and c not in seen:
            seen.add(c)
            ordered.append(c)

    canonical = _find_canonical(name)
    if canonical:
        add(canonical)
    add(name)
    return ordered
