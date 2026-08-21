"""Create clean raw Markdown for the P1 laws and judicial interpretations.

The script accepts downloaded official HTML files.  Keeping downloading outside
the extraction step makes the source material auditable and ensures that raw
Markdown contains only the legal text, not webpage navigation or footers.
"""
from __future__ import annotations

import argparse
import gzip
import html
import re
from html.parser import HTMLParser
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = PROJECT_ROOT / "data" / "raw"


class BlockExtractor(HTMLParser):
    """Collect paragraph-like text while excluding page scripts and styles."""

    BLOCK_TAGS = {"p", "h1", "h2", "h3", "h4", "li"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[str] = []
        self._depth = 0
        self._parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in {"script", "style", "noscript"}:
            self._skip += 1
        if not self._skip and tag in self.BLOCK_TAGS:
            if self._depth == 0:
                self._parts = []
            self._depth += 1
        if not self._skip and tag == "br" and self._depth:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self._skip:
            self._skip -= 1
        if not self._skip and tag in self.BLOCK_TAGS and self._depth:
            self._depth -= 1
            if self._depth == 0:
                value = "".join(self._parts).strip()
                if value:
                    self.blocks.append(value)

    def handle_data(self, data: str) -> None:
        if not self._skip and self._depth:
            self._parts.append(data)


class TextExtractor(HTMLParser):
    """Fallback extractor for official pages that do not use paragraph tags."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in {"script", "style", "noscript"}:
            self._skip += 1
        elif tag in {"p", "div", "br", "li", "h1", "h2", "h3", "h4"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self._skip:
            self._skip -= 1
        elif tag in {"p", "div", "li", "h1", "h2", "h3", "h4"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self.parts.append(data)


LAW_SPECS = {
    "产品质量法": ("product_quality.html", 74, "第七十四条", "中华人民共和国质量法"),
    "食品安全法": ("food_safety.html", 154, "第一百五十四条", "中华人民共和国食品安全法"),
    "旅游法": ("tourism.html", 112, "第一百一十二条", "中华人民共和国旅游法"),
    "广告法": ("advertising.html", 75, "第七十五条", "中华人民共和国广告法"),
    "著作权法": ("copyright.html", 67, "第六十七条", "中华人民共和国著作权法"),
    "商标法": ("trademark.html", 73, "第七十三条", "中华人民共和国商标法"),
    "专利法": ("patent.html", 82, "第八十二条", "中华人民共和国专利法"),
    "刑事诉讼法": ("criminal_procedure.html", 308, "第三百零八条", "中华人民共和国刑事诉讼法"),
    "反电信网络诈骗法": ("anti_telecom_fraud.html", 50, "第五十条", "中华人民共和国反电信网络诈骗法"),
    "民法典婚姻家庭编解释（一）": (
        "marriage_family_1.html", 91, "第九十一条", "最高人民法院关于适用《中华人民共和国民法典》婚姻家庭编的解释（一）",
    ),
    "民法典婚姻家庭编解释（二）": (
        "marriage_family_2.html", 23, "第二十三条", "最高人民法院关于适用《中华人民共和国民法典》婚姻家庭编的解释（二）",
    ),
    "民法典合同编通则解释": (
        "contract_general.html", 69, "第六十九条", "最高人民法院关于适用《中华人民共和国民法典》合同编通则若干问题的解释",
    ),
}

ARTICLE_RE = re.compile(r"^第[一二三四五六七八九十百千零〇\d]+条")
HEADING_RE = re.compile(r"^(?:第[一二三四五六七八九十百千零〇\d]+[编章节]|[一二三四五六七八九十]+、)")


def clean(text: str) -> str:
    text = html.unescape(text).replace("\xa0", " ").replace("\u3000", " ")
    return "\n".join(re.sub(r"\s+", "", line) for line in text.splitlines() if line.strip())


def legal_blocks(blocks: list[str], last_article: str) -> list[str]:
    blocks = [piece for block in blocks for piece in re.split(r"(?<=。)\s*(?=第[一二三四五六七八九十百千零〇\d]+条)", clean(block)) if piece]
    first_articles = [index for index, block in enumerate(blocks) if block.startswith("第一条")]
    if not first_articles:
        raise ValueError("未在 HTML 中识别出法条；请检查来源页面或提取规则。")
    # Pages may include a table of contents.  The last sequence that reaches the
    # statutory final article is the body rather than the navigation list.
    end = next((i for i, block in enumerate(blocks) if block.startswith(last_article)), None)
    if end is None:
        raise ValueError(f"未找到末条：{last_article}")
    # A contents section may mention chapter names, but normally does not have
    # full Article 1 text.  Start at the last Article 1 occurring before the
    # final article, then retain its immediately preceding structural heading.
    start = max(i for i in first_articles if i <= end)
    headings = [i for i in range(start) if HEADING_RE.match(blocks[i])]
    start = headings[-1] if headings else start
    return blocks[start : end + 1]


def fallback_legal_blocks(page_text: str, last_article: str) -> list[str]:
    """Extract articles from a page whose content is wrapped in generic divs."""
    text = clean(page_text)
    pieces = [piece for piece in re.split(r"(?<=。)\s*(?=第[一二三四五六七八九十百千零〇\d]+条)", text) if piece]
    first = next((i for i, piece in enumerate(pieces) if piece.startswith("第一条")), None)
    end = next((i for i, piece in enumerate(pieces) if piece.startswith(last_article)), None)
    if first is None or end is None or first > end:
        raise ValueError(f"未能从整页文本提取完整法条（末条：{last_article}）。")
    return pieces[first : end + 1]


def markdown_body(blocks: list[str]) -> str:
    result = []
    for block in blocks:
        if HEADING_RE.match(block):
            result.append("## " + block)
        else:
            result.append(block)
    return "\n\n".join(result) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--laws", nargs="*", choices=LAW_SPECS)
    args = parser.parse_args()

    laws = args.laws or list(LAW_SPECS)
    for law in laws:
        html_name, expected_count, last_article, full_name = LAW_SPECS[law]
        source = args.source_dir / html_name
        raw = source.read_bytes()
        if raw.startswith(b"\x1f\x8b"):
            raw = gzip.decompress(raw)
        page = raw.decode("utf-8", errors="ignore")
        extractor = BlockExtractor()
        extractor.feed(page)
        try:
            blocks = legal_blocks(extractor.blocks, last_article)
        except ValueError:
            if law == "广告法":
                # The official page puts the final effective-date clause
                # outside its content container.  It is retained verbatim.
                blocks = legal_blocks(extractor.blocks, "第七十四条")
                blocks.append("第七十五条　本法自2015年9月1日起施行。")
            else:
                # A few otherwise well-formed government pages place text
                # outside paragraph tags; tag stripping retains that text.
                plain_page = html.unescape(re.sub(r"<[^>]+>", "\n", page))
                blocks = fallback_legal_blocks(plain_page, last_article)
        body = markdown_body(blocks)
        count = len(re.findall(r"^第[一二三四五六七八九十百千零〇\d]+条", body, re.M))
        if count != expected_count:
            raise ValueError(f"{law} 条文数异常：{count}（预期 {expected_count}）")
        target = RAW_DIR / f"{law}.md"
        target.write_text(f"# {full_name}\n\n<!-- INFO END -->\n\n{body}", encoding="utf-8")
        print(f"[OK] {target.name}: {count} 条")


if __name__ == "__main__":
    main()
