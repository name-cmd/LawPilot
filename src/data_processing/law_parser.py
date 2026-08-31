"""
Parse Chinese law files in JSON and plain-text formats.
Each output LawArticle corresponds to one article (条文) with full metadata.
"""
import json
import re
from pathlib import Path
from typing import List, Optional
from dataclasses import dataclass, field


@dataclass
class LawArticle:
    law_name: str
    article_num: str       # "第一百八十四条"
    article_num_int: int   # 184
    content: str
    effective_date: str
    category: str
    part: str = ""         # 编，如 "第一编 总则"
    sub_part: str = ""     # 分编，如 "第一分编 通则"
    chapter: str = ""      # 章，如 "第二章 自然人"
    section: str = ""      # 节，如 "第二节 监护"
    status: str = "effective"       # effective | repealed | superseded
    repeal_date: str = ""
    superseded_by: str = ""
    law_version: str = ""


# fmt: off
_DIGIT_MAP = {
    '零': 0, '一': 1, '二': 2, '三': 3, '四': 4,
    '五': 5, '六': 6, '七': 7, '八': 8, '九': 9,
}
_UNIT_MAP = {'十': 10, '百': 100, '千': 1000}

# 兜底类别映射（registry 缺失时使用；registry 有细分类别则优先）
_CATEGORY_MAP = {
    '民法典': '民事法律', '合同法': '民事法律', '婚姻法': '民事法律',
    '继承法': '民事法律', '物权法': '民事法律', '侵权责任法': '民事法律',
    '刑法': '刑事法律', '刑事诉讼法': '诉讼法律', '民事诉讼法': '诉讼法律',
    '行政诉讼法': '诉讼法律', '行政处罚法': '行政法律', '行政许可法': '行政法律',
    '行政复议法': '行政法律', '道路交通安全法': '行政法律',
    '反电信网络诈骗法': '刑事法律', '食品安全法': '行政法律',
    '产品质量法': '行政法律', '旅游法': '行政法律', '广告法': '行政法律',
    '著作权法': '民事法律', '商标法': '民事法律', '专利法': '民事法律',
    '消费者权益保护法': '消费者权益保护法律',
    '劳动法': '劳动法律', '劳动合同法': '劳动法律', '社会保险法': '劳动与社会保障法律',
    '劳动争议调解仲裁法': '劳动法律',
    '工伤保险条例': '劳动行政法规', '劳动合同法实施条例': '劳动行政法规',
    '民事诉讼法解释': '诉讼司法解释', '劳动争议': '劳动司法解释',
    '民法典婚姻家庭编解释': '民事司法解释', '民法典合同编通则解释': '民事司法解释',
    '公司法': '商事法律', '证券法': '商事法律', '破产法': '商事法律',
}
# fmt: on


def _chinese_to_int(s: str) -> int:
    result = 0
    current = 0
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


def _parse_num(num_str: str) -> int:
    if num_str.isdigit():
        return int(num_str)
    try:
        return _chinese_to_int(num_str)
    except Exception:
        return 0


def _get_category(law_name: str) -> str:
    for key, cat in _CATEGORY_MAP.items():
        if key in law_name:
            return cat
    return '其他法律'


# Article header pattern: 第X条 followed by content until next 第X条
_ARTICLE_RE = re.compile(
    r'第([一二三四五六七八九十百千零\d]+)条\s*(.+?)(?=第[一二三四五六七八九十百千零\d]+条|$)',
    re.DOTALL,
)
_CHAPTER_RE = re.compile(r'第[一二三四五六七八九十百千零\d]+章\s+[^\n]+')


class LawParser:
    """Parse law files (JSON or plain text) into LawArticle lists."""

    def parse_directory(self, data_dir: str) -> List[LawArticle]:
        articles: List[LawArticle] = []
        root = Path(data_dir)
        for p in root.rglob('*.json'):
            articles.extend(self.parse_json(str(p)))
        for p in root.rglob('*.txt'):
            articles.extend(self.parse_text(str(p)))
        return articles

    # ------------------------------------------------------------------
    # JSON parsing
    # ------------------------------------------------------------------

    def parse_json(self, file_path: str) -> List[LawArticle]:
        with open(file_path, encoding='utf-8') as f:
            data = json.load(f)
        if isinstance(data, list):
            result = []
            for item in data:
                result.extend(self._parse_law_dict(item))
            return result
        return self._parse_law_dict(data)

    def _parse_law_dict(self, data: dict) -> List[LawArticle]:
        law_name = data.get('title') or data.get('name') or data.get('law_name') or '未知法律'
        effective_date = data.get('effective_date') or data.get('publish_date') or ''
        # 优先用 registry 嵌入的细分类别（如"劳动司法解释"），缺失时用兜底映射
        category = data.get('category') or _get_category(law_name)
        content = data.get('content') or data.get('articles') or []

        if isinstance(content, str):
            return self._parse_text_content(law_name, content, effective_date, category)

        articles: List[LawArticle] = []
        for item in content:
            if not isinstance(item, dict):
                continue
            if 'articles' in item:
                chapter = item.get('chapter') or item.get('title') or ''
                for art in item['articles']:
                    a = self._parse_article_dict(art, law_name, effective_date, category, chapter)
                    if a:
                        articles.append(a)
            else:
                a = self._parse_article_dict(item, law_name, effective_date, category)
                if a:
                    articles.append(a)
        return articles

    def _parse_article_dict(
        self, data: dict, law_name: str, effective_date: str,
        category: str, chapter: str = ''
    ) -> Optional[LawArticle]:
        num_str = str(
            data.get('article_number')
            or data.get('article_num')
            or data.get('number')
            or data.get('index')
            or ''
        )
        content = str(data.get('content') or data.get('text') or '').strip()
        if not num_str or not content:
            return None
        num_clean = num_str.replace('条', '').replace('第', '')
        article_num_int = data.get('article_num_int')
        if article_num_int is None:
            article_num_int = _parse_num(num_clean)
        else:
            article_num_int = int(article_num_int)

        part = str(data.get('part') or '')
        sub_part = str(data.get('sub_part') or '')
        article_chapter = str(data.get('chapter') or chapter or '')
        section = str(data.get('section') or '')

        return LawArticle(
            law_name=law_name,
            article_num=f'第{num_clean}条' if '条' not in num_str else num_str,
            article_num_int=article_num_int,
            content=content,
            effective_date=effective_date,
            category=category,
            part=part,
            sub_part=sub_part,
            chapter=article_chapter,
            section=section,
            status=str(data.get("status") or "effective"),
            repeal_date=str(data.get("repeal_date") or ""),
            superseded_by=str(data.get("superseded_by") or ""),
            law_version=str(data.get("law_version") or ""),
        )

    # ------------------------------------------------------------------
    # Plain-text parsing
    # ------------------------------------------------------------------

    def parse_text(self, file_path: str) -> List[LawArticle]:
        with open(file_path, encoding='utf-8') as f:
            text = f.read()
        law_name = Path(file_path).stem
        m = re.search(r'^(.{2,20}(?:法典|法律|法规|条例|规定|办法|法))', text[:300], re.M)
        if m:
            law_name = m.group(1).strip()
        return self._parse_text_content(law_name, text, '', _get_category(law_name))

    def _parse_text_content(
        self, law_name: str, text: str, effective_date: str, category: str
    ) -> List[LawArticle]:
        articles = []
        chapter = ''
        prev_end = 0

        for ch_m in _CHAPTER_RE.finditer(text):
            chapter = ch_m.group(0).strip()

        for m in _ARTICLE_RE.finditer(text):
            num_str = m.group(1)
            content = m.group(2).strip()
            if not content:
                continue
            articles.append(LawArticle(
                law_name=law_name,
                article_num=f'第{num_str}条',
                article_num_int=_parse_num(num_str),
                content=content,
                effective_date=effective_date,
                category=category,
                chapter=chapter,
            ))
        return articles
