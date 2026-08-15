"""Create clean raw Markdown for the four P1 administrative laws.

The script deliberately accepts downloaded HTML files as input.  This keeps the
download step auditable and separates it from the extraction logic; the output
contains only the law text, its version note, and structural headings.
"""
from __future__ import annotations

import argparse
import html
import re
from html.parser import HTMLParser
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = PROJECT_ROOT / "data" / "raw"


class ParagraphExtractor(HTMLParser):
    """Extract paragraph-like blocks while ignoring scripts and styles."""

    # Law pages put the body in ``p`` tags (often with nested spans).  Capturing
    # enclosing divs too would collapse an entire page into one giant block.
    BLOCK_TAGS = {"p", "h1", "h2", "h3", "li"}

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
                text = "".join(self._parts).strip()
                if text:
                    self.blocks.append(text)

    def handle_data(self, data: str) -> None:
        if not self._skip and self._depth:
            self._parts.append(data)


LAW_SPECS = {
    "行政处罚法": {
        "html": "admin_penalty.html",
        "preamble": "（1996年3月17日第八届全国人民代表大会第四次会议通过；经2009年、2017年修正，2021年1月22日第十三届全国人民代表大会常务委员会第二十五次会议修订）\n自2021年7月15日起施行。",
        "last_article": "第八十六条",
        "expected_articles": 86,
    },
    "行政许可法": {
        "html": "admin_license.html",
        "preamble": "（2003年8月27日第十届全国人民代表大会常务委员会第四次会议通过；根据2019年4月23日第十三届全国人民代表大会常务委员会第十次会议《关于修改〈中华人民共和国建筑法〉等八部法律的决定》修正）\n现行文本为2019年修正文本。",
        "last_article": "第八十三条",
        "expected_articles": 83,
    },
    "行政复议法": {
        "html": "admin_reconsideration.html",
        "preamble": "（1999年4月29日第九届全国人民代表大会常务委员会第九次会议通过；经2009年、2017年修正，2023年9月1日第十四届全国人民代表大会常务委员会第五次会议修订）\n自2024年1月1日起施行。",
        "last_article": "第九十条",
        "expected_articles": 90,
    },
    "行政诉讼法": {
        "html": "admin_litigation.html",
        "preamble": "（1989年4月4日第七届全国人民代表大会第二次会议通过；经2014年、2017年修正）\n现行文本为2017年第二次修正文本。",
        "last_article": "第一百零三条",
        "expected_articles": 103,
    },
}

ARTICLE_RE = re.compile(r"^第[一二三四五六七八九十百千零〇\d]+条")
CHAPTER_RE = re.compile(r"^第[一二三四五六七八九十百千零〇\d]+章")
SECTION_RE = re.compile(r"^第[一二三四五六七八九十百千零〇\d]+节")


def clean_block(text: str) -> str:
    text = html.unescape(text).replace("\xa0", " ").replace("\u3000", " ")
    lines = []
    for line in text.splitlines():
        line = re.sub(r"\s+", "", line)
        if line:
            lines.append(line)
    return "\n".join(lines)


def law_body(blocks: list[str], last_article: str) -> str:
    blocks = [clean_block(block) for block in blocks]
    article_index = next(i for i, block in enumerate(blocks) if ARTICLE_RE.match(block))
    chapter_index = max(
        (i for i in range(article_index) if CHAPTER_RE.match(blocks[i])), default=article_index
    )
    body = []
    for block in blocks[chapter_index:]:
        if CHAPTER_RE.match(block) or SECTION_RE.match(block):
            # The HTML normalisation removes indentation, so restore the space
            # required by the Markdown converter's hierarchy recogniser.
            heading = re.sub(
                r"^(第[一二三四五六七八九十百千零〇\d]+[章节])", r"\1 ", block, count=1
            )
            body.append("## " + heading)
        else:
            body.append(block)
        if block.startswith(last_article):
            break
    if not body or not body[-1].startswith(last_article):
        raise ValueError(f"未找到末条 {last_article}")
    return "\n\n".join(body) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", type=Path, required=True)
    args = parser.parse_args()

    for name, spec in LAW_SPECS.items():
        source = args.source_dir / spec["html"]
        parser_ = ParagraphExtractor()
        parser_.feed(source.read_text(encoding="utf-8", errors="ignore"))
        body = law_body(parser_.blocks, spec["last_article"])
        count = len(re.findall(r"^第[一二三四五六七八九十百千零〇\d]+条", body, re.M))
        if count != spec["expected_articles"]:
            raise ValueError(f"{name} 条文数异常：{count}（预期 {spec['expected_articles']}）")
        content = f"# 中华人民共和国{name}\n\n{spec['preamble']}\n\n<!-- INFO END -->\n\n{body}"
        target = RAW_DIR / f"{name}.md"
        target.write_text(content, encoding="utf-8")
        print(f"[OK] {target.name}: {count} 条")


if __name__ == "__main__":
    main()
