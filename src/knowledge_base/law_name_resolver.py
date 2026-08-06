"""Resolve cited law names to canonical names used in the vector store metadata."""
from typing import List, Optional

# Canonical names match data/raw/*.md filename stems.
KNOWN_LAWS = ("民法典", "宪法", "劳动法", "民事诉讼法")

_ALIASES = {
    "民法": "民法典",
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
