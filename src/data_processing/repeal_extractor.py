"""
Extract law repeal relationships from Chinese law text (e.g. 民法典末条「同时废止」).
Outputs structured repeal records for law_registry merge and KB build.
"""
import json
import re
from pathlib import Path
from typing import Dict, List, Optional

# 《中华人民共和国婚姻法》、《合同法》…同时废止
_REPEAL_CLAUSE_RE = re.compile(
    r"《([^》]+)》[^。]*?同时废止|同时废止[^。]*?《([^》]+)》"
)
_BULK_REPEAL_RE = re.compile(
    r"《([^》]+)》(?:[、，]|和|及)*"
)
_EFFECTIVE_REPEAL_LINE_RE = re.compile(
    r"自\s*(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日.*?同时废止",
    re.DOTALL,
)


def _normalize_law_name(full_name: str) -> str:
    """Strip 中华人民共和国 prefix for registry keys."""
    name = full_name.strip()
    if name.startswith("中华人民共和国"):
        name = name[len("中华人民共和国") :]
    return name.strip()


def extract_repealed_laws_from_text(text: str) -> List[str]:
    """Return list of repealed law short names mentioned in a repeal clause."""
    if "废止" not in text:
        return []

    names: List[str] = []
    seen: set = set()

    # Find sentences containing 同时废止
    for sentence in re.split(r"[。\n]", text):
        if "同时废止" not in sentence and "废止" not in sentence:
            continue
        for m in _BULK_REPEAL_RE.finditer(sentence):
            short = _normalize_law_name(m.group(1))
            if short and short not in seen:
                seen.add(short)
                names.append(short)
    return names


def extract_repeal_date_from_text(text: str) -> str:
    """Return ISO date YYYY-MM-DD from 自YYYY年M月D日起施行…废止 pattern."""
    m = _EFFECTIVE_REPEAL_LINE_RE.search(text)
    if m:
        y, mo, d = m.groups()
        return f"{y}-{int(mo):02d}-{int(d):02d}"
    return ""


def extract_from_article(
    law_name: str,
    article_content: str,
    effective_date: str = "",
) -> List[Dict]:
    """
    If article_content is a repeal clause, return repeal records for each cited law.
    """
    repealed = extract_repealed_laws_from_text(article_content)
    if not repealed:
        return []

    repeal_date = extract_repeal_date_from_text(article_content) or effective_date
    superseding = _normalize_law_name(law_name)

    records = []
    for name in repealed:
        records.append({
            "law_name": name,
            "status": "repealed",
            "repeal_date": repeal_date,
            "superseded_by": superseding,
            "note": f"由《{law_name}》废止条款自动抽取",
        })
    return records


def extract_from_processed_json(json_path: str) -> List[Dict]:
    """Scan a processed law JSON for repeal clauses in article content."""
    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)

    law_name = data.get("title") or data.get("name") or Path(json_path).stem
    effective_date = data.get("effective_date") or ""
    articles = data.get("articles") or data.get("content") or []

    all_records: List[Dict] = []
    seen: set = set()

    if isinstance(articles, list):
        for art in articles:
            if not isinstance(art, dict):
                continue
            content = str(art.get("content") or art.get("text") or "")
            for rec in extract_from_article(law_name, content, effective_date):
                key = rec["law_name"]
                if key not in seen:
                    seen.add(key)
                    all_records.append(rec)
    return all_records


def merge_registry(
    auto_records: List[Dict],
    manual_registry: Optional[Dict] = None,
) -> Dict:
    """Merge auto-extracted repeals with manual law_registry.json."""
    merged: Dict = dict(manual_registry or {})
    for rec in auto_records:
        key = rec["law_name"]
        if key not in merged:
            merged[key] = {
                "status": rec.get("status", "repealed"),
                "repeal_date": rec.get("repeal_date", ""),
                "superseded_by": rec.get("superseded_by", ""),
                "note": rec.get("note", ""),
            }
    return merged


def load_manual_registry(path: str) -> Dict:
    p = Path(path)
    if not p.exists():
        return {}
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def save_registry(registry: Dict, path: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(registry, f, ensure_ascii=False, indent=2)


def extract_directory(processed_dir: str, output_path: str, registry_path: str) -> Dict:
    """Scan all JSON in processed_dir and write merged law_repeals.json."""
    all_auto: List[Dict] = []
    seen: set = set()
    for p in Path(processed_dir).rglob("*.json"):
        for rec in extract_from_processed_json(str(p)):
            if rec["law_name"] not in seen:
                seen.add(rec["law_name"])
                all_auto.append(rec)

    manual = load_manual_registry(registry_path)
    merged = merge_registry(all_auto, manual)
    save_registry(merged, output_path)
    return merged
