#!/usr/bin/env python3
"""Lightweight structural QA for processed legal data; no ML dependencies."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"
REQUIRED_METADATA = {
    "full_name", "status", "category", "issue_org", "effective_date",
    "law_version", "source",
}


def main() -> None:
    failures: list[str] = []
    total = 0
    for path in sorted(PROCESSED.glob("*.json")):
        if path.name == "law_repeals.json":
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        law = data.get("law_name", path.stem)
        articles = data.get("articles", [])
        numbers = [a.get("article_number") for a in articles]
        missing = sorted(key for key in REQUIRED_METADATA if not data.get(key))
        duplicated = sorted(number for number, count in Counter(numbers).items() if count > 1)
        if data.get("article_count") != len(articles):
            failures.append(f"{law}: article_count mismatch")
        if missing:
            failures.append(f"{law}: missing metadata: {', '.join(missing)}")
        if duplicated:
            failures.append(f"{law}: duplicate articles: {', '.join(duplicated[:3])}")
        if any(not str(a.get("content", "")).strip() for a in articles):
            failures.append(f"{law}: empty article content")
        total += len(articles)
        print(f"[OK] {law}: {len(articles)} articles")

    repeals = json.loads((PROCESSED / "law_repeals.json").read_text(encoding="utf-8"))
    bad = [name for name, record in repeals.items() if "checkpoint" in (name + json.dumps(record, ensure_ascii=False)).lower()]
    if bad:
        failures.append(f"law_repeals contains checkpoint data: {bad}")

    print(f"Checked {total} articles; checkpoint entries: {len(bad)}")
    if failures:
        raise SystemExit("\n".join(failures))


if __name__ == "__main__":
    main()
