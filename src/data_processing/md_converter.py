"""
Convert Markdown law documents to structured JSON for LawParser / RAG.

Law name: taken from the .md filename stem (user-controlled; see scripts/convert_md_to_json.py).
Hierarchy: optional part / sub_part / chapter / section — only levels present in the
source are filled; hierarchy_path aggregates non-empty levels for retrieval and citation.
"""
import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .law_parser import _parse_num

# **第一条** or plain 第一条
_ARTICLE_BOLD_RE = re.compile(
    r"^\*\*第([一二三四五六七八九十百千零\d]+)条\*\*\s*(.*)$"
)
_ARTICLE_PLAIN_RE = re.compile(
    r"^第([一二三四五六七八九十百千零\d]+)条\s*(.*)$"
)
_HEADER_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_TOC_LINK_RE = re.compile(r"^\[.+\]\(#.+\)\s*$")

# Labeled effective / enforcement dates (prefer these over dates in preamble narrative)
_EFFECTIVE_DATE_PATTERNS = [
  # 生效日期：2021 年 1 月 1 日 / 施行时间：2018年3月11日
    re.compile(
        r"(?:生效日期|施行时间|实施时间|执行时间|施行日期)"
        r"[：:]\s*(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日"
    ),
    re.compile(
        r"(?:生效日期|施行时间|实施时间|执行时间|施行日期)"
        r"[：:]\s*(\d{4})年(\d{1,2})月(\d{1,2})日"
    ),
    # 自 2021 年 1 月 1 日起施行
    re.compile(
        r"自\s*(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日起?\s*施行"
    ),
    re.compile(
        r"自\s*(\d{4})年(\d{1,2})月(\d{1,2})日起?\s*施行"
    ),
]

_PART_RE = re.compile(r"^第[一二三四五六七八九十百千零\d]+编\s+")
_SUB_PART_RE = re.compile(r"^第[一二三四五六七八九十百千零\d]+分编\s+")
_CHAPTER_RE = re.compile(r"^第[一二三四五六七八九十百千零\d]+章\s+")
_SECTION_RE = re.compile(r"^第[一二三四五六七八九十百千零\d]+节\s+")
_SPECIAL_PARTS = frozenset({"附则", "序言", "导言", "总则"})

_HIERARCHY_KEYS = ("part", "sub_part", "chapter", "section")


def law_name_from_source(source_name: str) -> str:
    """Derive canonical law name from .md filename (stem)."""
    if not source_name:
        return "未知法律"
    return Path(source_name).stem


def _format_article_number(num_raw: str) -> str:
    s = num_raw.strip().replace("第", "").replace("条", "")
    return f"第{s}条"


def _extract_effective_date(text: str) -> str:
    """Return ISO date YYYY-MM-DD from preamble metadata, or ''."""
    for pattern in _EFFECTIVE_DATE_PATTERNS:
        m = pattern.search(text)
        if m:
            y, mo, d = m.groups()
            return f"{y}-{int(mo):02d}-{int(d):02d}"
    return ""


def _extract_metadata(text: str, law_name: str) -> Tuple[str, str]:
    """Returns (law_name, effective_date). Name comes only from filename."""
    return law_name, _extract_effective_date(text)


def _classify_heading(title: str) -> Optional[str]:
    """
    Classify heading by legal structure keywords (not Markdown level).

    Returns: part | sub_part | chapter | section | None
    """
    title = title.strip()
    if title in _SPECIAL_PARTS:
        return "part"
    if _SUB_PART_RE.match(title):
        return "sub_part"
    if _PART_RE.match(title):
        return "part"
    if _SECTION_RE.match(title):
        return "section"
    if _CHAPTER_RE.match(title):
        return "chapter"
    return None


def _apply_heading(
    kind: str,
    title: str,
    part: str,
    sub_part: str,
    chapter: str,
    section: str,
) -> Tuple[str, str, str, str]:
    if kind == "part":
        return title, "", "", ""
    if kind == "sub_part":
        return part, title, "", ""
    if kind == "chapter":
        return part, sub_part, title, ""
    if kind == "section":
        return part, sub_part, chapter, title
    return part, sub_part, chapter, section


def _hierarchy_path(part: str, sub_part: str, chapter: str, section: str) -> List[str]:
    return [p for p in (part, sub_part, chapter, section) if p]


def _match_article_line(stripped: str) -> Optional[re.Match]:
    m = _ARTICLE_BOLD_RE.match(stripped)
    if m:
        return m
    if _TOC_LINK_RE.match(stripped):
        return None
    return _ARTICLE_PLAIN_RE.match(stripped)


def _find_body_start(lines: List[str]) -> int:
    """Skip title block and TOC; start at first structural heading or article."""
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        if _match_article_line(stripped):
            return i
        hm = _HEADER_RE.match(stripped)
        if hm:
            heading = hm.group(2).strip()
            if heading.startswith("[") and "](#" in heading:
                continue
            if stripped.startswith("- ") and "[#" in stripped:
                continue
            if _classify_heading(heading):
                return i
    return 0


def _infer_hierarchy_schema(articles: List[Dict]) -> List[str]:
    """Which hierarchy levels appear in at least one article (stable order)."""
    used = {k: False for k in _HIERARCHY_KEYS}
    for art in articles:
        for k in _HIERARCHY_KEYS:
            if art.get(k):
                used[k] = True
    return [k for k in _HIERARCHY_KEYS if used[k]]


def _article_record(
    num_raw: str,
    content: str,
    part: str,
    sub_part: str,
    chapter: str,
    section: str,
) -> Dict:
    path = _hierarchy_path(part, sub_part, chapter, section)
    return {
        "article_number": _format_article_number(num_raw),
        "article_num_int": _parse_num(num_raw),
        "part": part,
        "sub_part": sub_part,
        "chapter": chapter,
        "section": section,
        "hierarchy_path": path,
        "hierarchy_text": " / ".join(path),
        "content": content,
    }


def parse_markdown_law(text: str, source_name: str = "") -> Dict:
    """
    Parse one Markdown law file into a JSON-serialisable dict.

    Articles: **第X条** or 第X条 at line start (multi-line body supported).
    """
    law_name = law_name_from_source(source_name)
    law_name, effective_date = _extract_metadata(text, law_name)

    lines = text.splitlines()
    body_start = _find_body_start(lines)

    part, sub_part, chapter, section = "", "", "", ""
    articles: List[Dict] = []
    current: Optional[Dict] = None

    def flush_article() -> None:
        nonlocal current
        if not current:
            return
        content = current["content"].strip()
        if content:
            articles.append(
                _article_record(
                    current["num_raw"],
                    content,
                    current["part"],
                    current["sub_part"],
                    current["chapter"],
                    current["section"],
                )
            )
        current = None

    for line in lines[body_start:]:
        stripped = line.strip()

        if not stripped:
            if current:
                current["content"] += "\n"
            continue

        if stripped.startswith("- ") and "[#" in stripped:
            continue

        hm = _HEADER_RE.match(stripped)
        if hm and not stripped.startswith("**"):
            heading = hm.group(2).strip()
            if heading.startswith("[") and "](#" in heading:
                continue
            kind = _classify_heading(heading)
            if kind:
                part, sub_part, chapter, section = _apply_heading(
                    kind, heading, part, sub_part, chapter, section
                )
            continue

        am = _match_article_line(stripped)
        if am:
            flush_article()
            current = {
                "num_raw": am.group(1),
                "content": am.group(2),
                "part": part,
                "sub_part": sub_part,
                "chapter": chapter,
                "section": section,
            }
            continue

        if current is not None:
            if current["content"]:
                current["content"] += "\n" + stripped
            else:
                current["content"] = stripped

    flush_article()

    schema = _infer_hierarchy_schema(articles)

    return {
        "title": law_name,
        "law_name": law_name,
        "effective_date": effective_date,
        "source_file": source_name,
        "article_count": len(articles),
        "hierarchy_schema": schema,
        "articles": articles,
    }


def convert_md_file(md_path: Path, output_dir: Path) -> Path:
    text = md_path.read_text(encoding="utf-8")
    data = parse_markdown_law(text, source_name=md_path.name)
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / f"{md_path.stem}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return out_path


def convert_md_directory(
    input_dir: Path,
    output_dir: Path,
    *,
    recursive: bool = True,
) -> List[Tuple[Path, Path, int]]:
    pattern = "**/*.md" if recursive else "*.md"
    md_files = sorted(input_dir.glob(pattern))
    results: List[Tuple[Path, Path, int]] = []

    for md_path in md_files:
        text = md_path.read_text(encoding="utf-8")
        data = parse_markdown_law(text, source_name=md_path.name)
        output_dir.mkdir(parents=True, exist_ok=True)
        out_path = output_dir / f"{md_path.stem}.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        results.append((md_path, out_path, data["article_count"]))

    return results
