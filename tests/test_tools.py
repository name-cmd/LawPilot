"""工具执行器单测：检索法条 / 查询时效（用假 store 与临时注册表）。"""
import json
import tempfile
from pathlib import Path

from langchain_core.documents import Document

from src.agents.tools import TOOLS, execute_tool
from src.knowledge_base.law_validity import LawValidityService


class FakeStore:
    """只实现相似度检索的假 store（距离：0=最近，1=最远）。"""

    def __init__(self, results):
        self._results = results

    def similarity_search_unique(self, query, k=None):
        return self._results


def _doc(law: str, num: str, text: str) -> Document:
    return Document(page_content=text, metadata={"law_name": law, "article_num": num, "status": "effective"})


def test_tools_contain_two_functions():
    names = {t["function"]["name"] for t in TOOLS}
    assert names == {"search_articles", "check_law_validity"}


def test_search_articles_hit():
    store = FakeStore([
        (_doc("工伤保险条例", "第十七条", "职工发生事故伤害，所在单位应当自事故伤害发生之日起30日内提出工伤认定申请。"), 0.2),
        (_doc("工伤保险条例", "第十八条", "提出工伤认定申请应当提交下列材料。"), 1.5),  # 低于阈值 0.35，应被过滤
    ])
    out = execute_tool("search_articles", {"query": "工伤认定时效", "law_name": "工伤保险条例"}, store=store)
    assert out["count"] == 1
    assert out["articles"][0]["law_name"] == "工伤保险条例"
    assert out["articles"][0]["article_num"] == "第十七条"


def test_search_articles_empty_query():
    out = execute_tool("search_articles", {"query": "   "}, store=FakeStore([]))
    assert out["count"] == 0 and out["note"]


def test_check_validity():
    d = tempfile.TemporaryDirectory()
    p = Path(d.name) / "law_registry.json"
    p.write_text(json.dumps({
        "婚姻法": {"status": "repealed", "repeal_date": "2021-01-01", "superseded_by": "民法典"},
    }, ensure_ascii=False), encoding="utf-8")
    svc = LawValidityService(registry_path=str(p))
    out = execute_tool("check_law_validity", {"law_name": "婚姻法"}, validity=svc)
    assert out["effective"] is False
    assert out["superseded_by"] == "民法典"
    out2 = execute_tool("check_law_validity", {"law_name": "劳动合同法"}, validity=svc)
    assert out2["effective"] is True


def test_unknown_tool_returns_error():
    out = execute_tool("no_such_tool", {})
    assert "error" in out


def test_arg_sanitized():
    out = execute_tool("search_articles", {"query": "a" * 500}, store=FakeStore([]))
    assert out["count"] == 0  # 超长参数被截断后检索不到，不抛异常
